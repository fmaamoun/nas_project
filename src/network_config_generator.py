import ipaddress
from datetime import datetime, timezone


class NetworkConfigGenerator:
    def __init__(self, intent):
        self.__intent = intent
        self.__as_map, self.__backbone_as_num = self.__init_as_map()
        self.__routers = self.__create_router_map()
        self.__assign_ips()

    # Initialize the AS map and IP address iterators
    def __init_as_map(self):
        # Create a map AS_number → AS_details
        as_map = {a["as_number"]: a for a in self.__intent["as"]}

        # Add iterators for Loopback and physical subnets
        for num, a in as_map.items():
            a["loopback_iter"] = (
                ipaddress.IPv4Network(a["ipv4_ranges"]["loopback"]).hosts()
                if "loopback" in a["ipv4_ranges"] else None
            )
            a["phys_iter"] = (
                ipaddress.IPv4Network(a["ipv4_ranges"]["physical"]).subnets(new_prefix=24)
            )

        # Identify the backbone AS
        backbone_as_num = next(num for num, a in as_map.items() if a.get("backbone", False))
        return as_map, backbone_as_num

    # Build the router map (PE, P, CE)
    def __create_router_map(self):
        routers = {}
        for kind, rtype in [("pe_routers", "PE"), ("p_routers", "P"), ("ce_routers", "CE")]:
            for r in self.__intent.get(kind, []):
                # Use specific AS for CE, otherwise use backbone
                as_num = r.get("as_number") if rtype == "CE" else self.__backbone_as_num
                routers[r["hostname"]] = {
                    "type": rtype,
                    "as": as_num,
                    "vrfs": r.get("vrfs", []),
                    "interfaces": { i["name"]: dict(i) for i in r["interfaces"] }
                }

                if rtype == "CE":
                    routers[r["hostname"]]["private_network"] = r.get("private_network")
                    routers[r["hostname"]]["interfaces"]["Loopback0"] = {"name": "Loopback0"}

        return routers

    # Assign IP addresses to Loopback and physical interfaces
    def __assign_ips(self):
        # Assign Loopback IPs
        for router in self.__routers.values():
            iface = router["interfaces"].get("Loopback0")
            if iface and self.__as_map[router["as"]]["loopback_iter"]:
                ip = str(next(self.__as_map[router["as"]]["loopback_iter"]))
                iface.update({"ip": ip, "mask": "255.255.255.255", "internal": True})
            elif router["type"] == "CE":
                network = ipaddress.IPv4Network(router["private_network"])
                iface.update({"ip": network.network_address.__str__(), "mask": network.netmask.__str__(), "internal": False, "ce_test": True})

        # Assign physical IPs to links/subnets
        for link in self.__intent["subnets"]:
            if any(self.__routers[ep["router"]]["type"] == "CE" for ep in link):
                ce_ep = next(ep for ep in link if self.__routers[ep["router"]]["type"] == "CE")
                net = next(self.__as_map[self.__routers[ce_ep["router"]]["as"]]["phys_iter"])
            else:
                net = next(self.__as_map[self.__backbone_as_num]["phys_iter"])
            hosts = list(net.hosts())

            # Assign an address to each endpoint
            for idx, ep in enumerate(link):
                iface = self.__routers[ep["router"]]["interfaces"][ep["interface"]]
                iface.update({
                    "ip": str(hosts[idx]),
                    "mask": "255.255.255.0",
                    "mpls": self.__routers[ep["router"]]["type"] != "CE",
                    "internal": self.__routers[ep["router"]]["type"] != "CE"
                })

    # Build the configuration of an interface
    def __build_interface_config(self, iface, as_num, vrf_name=None):
        print(iface)
        lines = [f"interface {iface['name']}"]

        # Add VRF if applicable
        if vrf_name:
            lines.append(f" ip vrf forwarding {vrf_name}")

        # IP address
        if "ip" in iface:
            lines.append(f" ip address {iface['ip']} {iface['mask']}")

        # OSPF for internal or Loopback interfaces
        if iface.get("internal") or iface['name'] == "Loopback0":
            if not iface.get("ce_test"):
                if not vrf_name:
                    lines.append(f" ip ospf 1 area {as_num}")
                    if "ospf_cost" in iface:
                        lines.append(f" ip ospf cost {iface['ospf_cost']}")

        # Auto-negotiation for physical interfaces
        if "GigabitEthernet" in iface['name']:
            lines.append(" negotiation auto")

        lines.append("!")
        return lines

    # Find the CE router connected to a PE via a specific interface
    def __find_ce_peer(self, pe, iface):
        for link in self.__intent["subnets"]:
            if any(e['router'] == pe and e['interface'] == iface for e in link):
                for ep in link:
                    if ep['router'] != pe and self.__routers[ep['router']]['type'] == 'CE':
                        ce = self.__routers[ep['router']]
                        return ce['interfaces'][ep['interface']]['ip'], ce['as']
        return '0.0.0.0', 0

    # Generate the MP-BGP configuration for a PE
    def __generate_mpbgp(self, router_name):
        r = self.__routers[router_name]
        lines = [f"router bgp {r['as']}", f" bgp router-id {r['interfaces']['Loopback0']['ip']}"]

        # iBGP sessions between PE (vpnv4)
        for peer_name, peer in self.__routers.items():
            if peer['type'] == 'PE' and peer_name != router_name:
                rip = peer['interfaces']['Loopback0']['ip']
                lines += [f" neighbor {rip} remote-as {r['as']}", f" neighbor {rip} update-source Loopback0"]

        # Enable vpnv4 address-family
        lines += [" !", " address-family vpnv4"]
        for peer_name, peer in self.__routers.items():
            if peer['type'] == 'PE' and peer_name != router_name:
                rip = peer['interfaces']['Loopback0']['ip']
                lines += [f"  neighbor {rip} activate", f"  neighbor {rip} send-community extended"]
        lines.append(" exit-address-family")

        # Configure CE neighbors per VRF
        for vrf in r['vrfs']:
            ce_ip, ce_as = self.__find_ce_peer(router_name, vrf['associated_interfaces'][0])
            lines += [
                "!",
                f" address-family ipv4 vrf {vrf['name']}",
                f"  neighbor {ce_ip} remote-as {ce_as}",
                f"  neighbor {ce_ip} activate",
                " exit-address-family"
            ]
        lines.append("!")
        return lines

    # Generate BGP configuration for a CE
    def __generate_ce_bgp(self, router_name):
        ce = self.__routers[router_name]
        pe_ip = '0.0.0.0'

        # Find the IP address of the connected PE
        for link in self.__intent["subnets"]:
            if any(e['router'] == router_name for e in link):
                for ep in link:
                    if ep['router'] != router_name and self.__routers[ep['router']]['type'] == 'PE':
                        pe_ip = self.__routers[ep['router']]['interfaces'][ep['interface']]['ip']

        lines = [f"router bgp {ce['as']}", f" neighbor {pe_ip} remote-as {self.__backbone_as_num}"]

        # Add networks to advertise
        for iface in ce['interfaces'].values():
            if 'ip' in iface:
                ip_net = ipaddress.IPv4Interface(f"{iface['ip']}/{iface['mask']}").network.network_address
                lines.append(f" network {ip_net} mask {iface['mask']}")

        lines.append("!")
        return lines

    # PUBLIC METHOD: Generate the full configuration of a router
    def generate_router_config(self, router_name):
        now = datetime.now(timezone.utc).strftime('%H:%M:%S UTC %a %b %d %Y')
        r = self.__routers[router_name]
        lines = [
            '!', '!', '!', f'! Last configuration change at {now}', '!', 'version 15.2',
            'service timestamps debug datetime msec', 'service timestamps log datetime msec',
            '!', f'hostname {router_name}', '!', 'no aaa new-model', 'ip cef', '!'
        ]

        # VRF configuration for PE
        if r['type'] == 'PE':
            for vrf in r['vrfs']:
                lines += [f"ip vrf {vrf['name']}", f" rd {vrf['rd']}"]
                lines += [f" route-target export {e}" for e in vrf['route_targets']['export']]
                lines += [f" route-target import {i}" for i in vrf['route_targets']['import']]
                lines.append('!')

        # Interfaces
        for name, iface in r['interfaces'].items():
            vrf = next((v['name'] for v in r['vrfs'] if name in v.get('associated_interfaces', [])), None)
            lines += self.__build_interface_config(iface, r['as'], vrf)

        # OSPF/MPLS for PE and P
        if r['type'] in ('PE', 'P'):
            rid = r['interfaces']['Loopback0']['ip']
            lines += ['router ospf 1', f' router-id {rid}', ' mpls ldp autoconfig', '!']

        # BGP depending on type
        if r['type'] == 'PE':
            lines += self.__generate_mpbgp(router_name)
        elif r['type'] == 'CE':
            lines += self.__generate_ce_bgp(router_name)

        lines += [
            'ip forward-protocol nd', '!', 'line con 0', ' exec-timeout 0 0',
            ' privilege level 15', ' logging synchronous', '!', 'end'
        ]
        return "\n".join(lines)

    # PUBLIC METHOD: Generate configurations for all routers
    def generate_all_configs(self):
        return {r: self.generate_router_config(r) for r in self.__routers}

    # PUBLIC METHOD: Generate a recap of all network subnets and their associated routers/interfaces
    def generate_network_recap(self):
        lines = []

        for link in self.__intent.get("subnets", []):
            # Identify subnet from first endpoint (sufficient since all share it)
            first_ep = link[0]
            subnet_ip = self.__routers[first_ep["router"]]["interfaces"][first_ep["interface"]]["ip"]
            subnet_mask = self.__routers[first_ep["router"]]["interfaces"][first_ep["interface"]]["mask"]
            network = ipaddress.IPv4Interface(f"{subnet_ip}/{subnet_mask}").network

            lines.append(f"\nSubnet: {network.with_prefixlen}")
            for ep in link:
                iface = self.__routers[ep["router"]]["interfaces"][ep["interface"]]
                lines.append(f"  - Router: {ep['router']} | Interface: {ep['interface']} | IP: {iface['ip']}")

        return "\n".join(lines) if len(lines) > 1 else "No network links defined."
