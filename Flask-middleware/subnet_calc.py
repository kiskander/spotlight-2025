from ipcalc import Network

def get_subnet_from_ip(ip_with_cidr):
    try:
        # Use ipcalc to calculate the subnet mask
        network = Network(ip_with_cidr)
        subnet_mask = str(network.netmask())
        return subnet_mask
    except Exception as e:
        logging.error(f"Error calculating subnet mask or gateway: {e}")
        return None
