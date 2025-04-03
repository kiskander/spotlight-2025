import logging
import os
import meraki
from flask import Flask, request, jsonify
from subnet_calc import get_subnet_from_ip

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Initialize Meraki dashboard
meraki_key = os.getenv('MERAKI_API_KEY')
dashboard = meraki.DashboardAPI(meraki_key)

@app.route('/netbox-webhook', methods=['POST'])
def handle_netbox_webhook():
    logging.info("Webhook triggered")
    payload = request.get_json()

    try:
        # Extract device data from NetBox payload
        netbox_device_name = payload['data']['name']
        netbox_serial_number = payload['data']['serial']
        netbox_ip_address_full = payload['data'].get('primary_ip4', {}).get('address', None)
        netbox_ip_address = netbox_ip_address_full.split('/')[0] if netbox_ip_address_full else None

        logging.info(f"Device {netbox_device_name} with serial {netbox_serial_number} received from NetBox.")
        logging.info(f"Extracted IP address: {netbox_ip_address}")

        # Fetch Meraki device inventory
        meraki_org_id = os.getenv('MERAKI_ORG_ID')
        devices = dashboard.organizations.getOrganizationInventoryDevices(meraki_org_id)
        logging.info(f"Fetched {len(devices)} devices from Meraki.")

        for device in devices:
            if device['serial'] == netbox_serial_number:
                # Initialize flags for updates
                update_name = False
                update_ip = False

                # Check for name change
                if device['name'] != netbox_device_name:
                    update_name = True
                    logging.info(f"Name change detected: {device['name']} -> {netbox_device_name}")

                # Check for IP address change
                if netbox_ip_address:
                    current_ip = device.get('lanIp', None)
                    if current_ip != netbox_ip_address:
                        update_ip = True
                        logging.info(f"IP change detected: {current_ip} -> {netbox_ip_address}")

                # Perform updates based on changes
                if update_name:
                    try:
                        logging.info(f"Updating device name for {netbox_serial_number}")
                        name_response = dashboard.devices.updateDevice(
                            serial=device['serial'],
                            name=netbox_device_name
                        )
                        logging.info(f"Name updated successfully: {name_response}")
                    except meraki.exceptions.APIError as e:
                        logging.error(f"Meraki API error while updating name: {e}")

                if update_ip:
                    ip_address_url = payload['data'].get('primary_ip4', {}).get('url', None)

                    if netbox_ip_address_full:
                        # Extract gateway IP from custom fields
                        gateway_ip = payload['data'].get('custom_fields', {}).get('gateway_ip', None)
                        logging.info(f"Extracted gateway IP from custom field: {gateway_ip}")

                        # Calculate subnet mask using the IP with CIDR
                        logging.info(f"Calculating subnet mask for {netbox_ip_address_full}")
                        subnet_mask = get_subnet_from_ip(netbox_ip_address_full)

                        logging.info(f"Calculated subnet mask: {subnet_mask}")

                        if subnet_mask and gateway_ip:
                            try:
                                # Update the Meraki management interface
                                logging.info(f"Updating management interface for device {netbox_serial_number}")
                                ip_response = dashboard.devices.updateDeviceManagementInterface(
                                    serial=device['serial'],
                                    wan1={
                                        'usingStaticIp': True,
                                        'staticIp': netbox_ip_address,
                                        'staticSubnetMask': subnet_mask,
                                        'staticGatewayIp': gateway_ip
                                    }
                                )
                                logging.info(f"Management interface updated successfully: {ip_response}")
                            except meraki.exceptions.APIError as e:
                                logging.error(f"Meraki API error while updating IP: {e}")
                        else:
                            logging.warning("Failed to calculate subnet mask or gateway IP. Skipping IP update.")
                    else:
                        logging.warning("No primary_ip4 field in the payload. Skipping IP update.")
                # Break after processing the matching device
                break
        else:
            logging.warning(f"No matching device found in Meraki for serial: {netbox_serial_number}")

    except Exception as e:
        logging.error(f"Error processing payload: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8080)
