import ipaddress
from datetime import datetime, timezone
from typing import Dict, List


class Interface:
    """Représentation d'une interface réseau sur un routeur."""

    def __init__(self, iface_intent: dict) -> None:
        self.name = iface_intent["name"]
        self.ip_address: str = None
        self.ip_mask: str = None
        self.mpls_enabled: bool = False
        self.is_internal: bool = False

    def generate_config(self, igp: str = "ospf", router_type: str = None, as_obj: "AS" = None,
                        associated_vrf: dict = None) -> List[str]:
        """
        Génère la configuration de l'interface.
        Si 'associated_vrf' est fourni, la configuration inclut également le VRF forwarding.
        """
        lines = [f"interface {self.name}"]
        if associated_vrf:
            lines.append(f" ip vrf forwarding {associated_vrf['name']}")
        if self.ip_address:
            lines.append(f" ip address {self.ip_address} {self.ip_mask}")
        # Ajout des commandes OSPF et négociation sur les interfaces de type GigabitEthernet
        if router_type in ["PE", "P"] and igp == "ospf" and as_obj:
            if self.is_internal or self.name == "Loopback0":
                lines.append(f" ip ospf 1 area {as_obj.as_number}")
        if "GigabitEthernet" in self.name:
            lines.append(" negotiation auto")
        lines.append("!")
        return lines


class AS:
    """Représentation d'un Système Autonome."""

    def __init__(self, as_intent: dict) -> None:
        self.as_number: int = as_intent["as_number"]
        self.backbone: bool = as_intent.get("backbone", False)
        self.ipv4_ranges: dict = as_intent["ipv4_ranges"]
        self.mpls_config = None  # Sera défini par MPLSConfig._initialize_routers

        # Initialisation des itérateurs d'adresses
        if "loopback" in self.ipv4_ranges:
            self.loopback_iterator = ipaddress.IPv4Network(self.ipv4_ranges["loopback"]).hosts()
        if "physical" in self.ipv4_ranges:
            self.physical_iterator = ipaddress.IPv4Network(self.ipv4_ranges["physical"]).subnets(new_prefix=24)


class Router:
    """Représente un routeur avec sa configuration complète."""

    def __init__(self, router_intent: dict, as_obj: AS, router_type: str) -> None:
        self.hostname: str = router_intent["hostname"]
        self.type: str = router_type
        self.as_obj: AS = as_obj
        self.interfaces: Dict[str, Interface] = {}
        self.vrfs: List[dict] = router_intent.get("vrfs", [])

        for iface in router_intent.get("interfaces", []):
            self.interfaces[iface["name"]] = Interface(iface)

    def generate_config_lines(self, pe_routers: Dict[str, "Router"] = None) -> List[str]:
        """Génère la configuration complète du routeur."""
        lines = self._generate_header()
        lines.extend(self._generate_interfaces())
        if self.type in ["PE", "P"]:
            lines.extend(self._generate_ospf())
        if self.type == "PE" and pe_routers:
            lines.extend(self._generate_mpbgp(pe_routers))
        if self.type == "CE":
            lines.extend(self._generate_ce_bgp())
        lines.extend(self._generate_footer())
        return lines

    def _generate_header(self) -> List[str]:
        """Génère l'en-tête de configuration."""
        now = datetime.now(timezone.utc).strftime('%H:%M:%S UTC %a %b %d %Y')
        lines = [
            "!",
            f"! Last configuration change at {now}",
            "!",
            "version 15.2",
            "service timestamps debug datetime msec",
            "service timestamps log datetime msec",
            "!",
            f"hostname {self.hostname}",
            "!",
            "no aaa new-model",
            "ip cef",
            "!"
        ]

        if self.type == "PE" and self.vrfs:
            for vrf in self.vrfs:
                lines.extend([
                                 f"ip vrf {vrf['name']}",
                                 f" rd {vrf['rd']}"
                             ] +
                             [f" route-target export {rt}" for rt in vrf["route_targets"]["export"]] +
                             [f" route-target import {rt}" for rt in vrf["route_targets"]["import"]] +
                             ["!"]
                             )

        return lines

    def _generate_interfaces(self) -> List[str]:
        """Génère la configuration des interfaces."""
        lines = []
        for iface_name, iface in self.interfaces.items():
            # Vérifier si l'interface est associée à une VRF
            associated_vrf = next((vrf for vrf in self.vrfs if iface_name in vrf.get("associated_interfaces", [])),
                                  None)
            lines.extend(
                iface.generate_config(router_type=self.type, as_obj=self.as_obj, associated_vrf=associated_vrf))
        return lines

    def _generate_ospf(self) -> List[str]:
        """Génère la configuration OSPF pour le backbone."""
        loopback = self.interfaces.get("Loopback0")
        router_id = loopback.ip_address if loopback and loopback.ip_address else "0.0.0.0"
        return [
            "router ospf 1",
            f" router-id {router_id}",
            " mpls ldp autoconfig",
            "!"
        ]

    def _get_ce_ip(self, vrf: dict) -> str:
        """Retourne l'adresse IP du CE connecté à la VRF."""
        associated_iface = vrf["associated_interfaces"][0]

        if not hasattr(self.as_obj, 'mpls_config') or not self.as_obj.mpls_config:
            return "0.0.0.0"

        for subnet in self.as_obj.mpls_config.subnets:
            if len(subnet) != 2:
                continue

            # Vérifier si ce sous-réseau contient l'interface associée à la VRF
            pe_endpoint = next((ep for ep in subnet if ep["router"] == self.hostname and
                                ep["interface"] == associated_iface), None)
            if not pe_endpoint:
                continue

            # Trouver l'autre extrémité (le CE)
            ce_endpoint = next((ep for ep in subnet if ep["router"] != self.hostname), None)
            if not ce_endpoint:
                continue

            # Obtenir l'adresse IP du CE
            ce_router = self.as_obj.mpls_config.routers[ce_endpoint["router"]]
            ce_iface = ce_router.interfaces[ce_endpoint["interface"]]

            return ce_iface.ip_address

        return "0.0.0.0"

    def _generate_mpbgp(self, pe_routers: Dict[str, "Router"]) -> List[str]:
        """Génère la configuration MP-BGP pour les PE."""
        lines = [
            f"router bgp {self.as_obj.as_number}",
            f" bgp router-id {self.interfaces['Loopback0'].ip_address}"
        ]

        # Suppression du print de debug
        for pe in pe_routers.values():
            if pe.hostname != self.hostname:
                neighbor_ip = pe.interfaces["Loopback0"].ip_address
                lines.append(f" neighbor {neighbor_ip} remote-as {self.as_obj.as_number}")
                lines.append(f" neighbor {neighbor_ip} update-source Loopback0")

        lines.extend([
            " !",
            " address-family vpnv4",
        ])

        for pe in pe_routers.values():
            if pe.hostname != self.hostname:
                neighbor_ip = pe.interfaces["Loopback0"].ip_address
                lines.append(f"  neighbor {neighbor_ip} activate")
                lines.append(f"  neighbor {neighbor_ip} send-community extended")

        lines.append(" exit-address-family")

        for vrf in self.vrfs:
            associated_iface = vrf["associated_interfaces"][0]
            ce_remote_as = self._get_ce_as(vrf)
            # Utiliser l'IP du CE au lieu de l'IP du PE
            ce_ip = self._get_ce_ip(vrf)
            lines.extend([
                "!",
                f" address-family ipv4 vrf {vrf['name']}",
                f"  neighbor {ce_ip} remote-as {ce_remote_as}",
                f"  neighbor {ce_ip} activate",
                " exit-address-family"
            ])

        lines.append("!")
        return lines

    def _get_ce_as(self, vrf: dict) -> int:
        """Retourne l'AS du CE connecté à la VRF."""
        if not hasattr(self.as_obj, 'mpls_config') or not self.as_obj.mpls_config:
            return 0

        for subnet in self.as_obj.mpls_config.subnets:
            if len(subnet) != 2:
                continue

            routers = {subnet[0]["router"], subnet[1]["router"]}
            if self.hostname not in routers:
                continue

            ce_router = next((r for r in routers if r != self.hostname), None)
            if not ce_router:
                continue

            router_type = self.as_obj.mpls_config.routers[ce_router].type

            if router_type == "CE":
                return self.as_obj.mpls_config.routers[ce_router].as_obj.as_number

        return 0

    def _generate_ce_bgp(self) -> List[str]:
        """Génère la configuration BGP pour les CE."""
        if not hasattr(self.as_obj, 'mpls_config') or not self.as_obj.mpls_config:
            return ["! Error: mpls_config not set on AS object"]

        pe_ip = None
        for subnet in self.as_obj.mpls_config.subnets:
            if len(subnet) == 2:
                router_names = [subnet[0]["router"], subnet[1]["router"]]
                if self.hostname in router_names:
                    # Trouver l'autre routeur (PE)
                    pe_router_name = router_names[0] if router_names[1] == self.hostname else router_names[1]
                    pe_router = self.as_obj.mpls_config.routers[pe_router_name]

                    # Trouver l'interface PE connectée à ce CE
                    pe_iface_name = subnet[0]["interface"] if subnet[0]["router"] == pe_router_name else subnet[1][
                        "interface"]
                    pe_iface = pe_router.interfaces[pe_iface_name]

                    pe_ip = pe_iface.ip_address
                    break

        if pe_ip is None:
            pe_ip = "0.0.0.0"

        # Configuration BGP de base
        lines = [
            f"router bgp {self.as_obj.as_number}",
            f" neighbor {pe_ip} remote-as {self.as_obj.mpls_config.backbone_as.as_number}",
        ]

        # Ajouter des commandes pour annoncer les réseaux du CE
        for iface_name, iface in self.interfaces.items():
            if iface.ip_address and iface.ip_mask:
                # Convertir l'adresse IP et le masque en entiers
                ip_parts = [int(p) for p in iface.ip_address.split('.')]
                mask_parts = [int(p) for p in iface.ip_mask.split('.')]

                # Calculer l'adresse réseau
                network_parts = [ip_parts[i] & mask_parts[i] for i in range(4)]
                network_address = '.'.join(str(p) for p in network_parts)

                # Ajouter la commande réseau
                lines.append(f" network {network_address} mask {iface.ip_mask}")

        lines.append("!")
        return lines

    def _generate_footer(self) -> List[str]:
        """Génère le pied de page de configuration."""
        return [
            "ip forward-protocol nd",
            "!",
            "line con 0",
            " exec-timeout 0 0",
            " privilege level 15",
            " logging synchronous",
            "!",
            "end"
        ]


class MPLSConfig:
    """Gestionnaire principal de configuration MPLS/VPN."""

    def __init__(self, intent: dict) -> None:
        self.intent: dict = intent
        self.as_objects: Dict[int, AS] = self._initialize_as()
        self.backbone_as: AS = self._get_backbone_as()
        self.routers: Dict[str, Router] = self._initialize_routers()
        self.subnets: List[List[dict]] = self.intent.get("subnets", [])
        self._assign_addresses()

    def _initialize_as(self) -> Dict[int, AS]:
        return {as_cfg["as_number"]: AS(as_cfg) for as_cfg in self.intent.get("as", [])}

    def _get_backbone_as(self) -> AS:
        for as_obj in self.as_objects.values():
            if as_obj.backbone:
                return as_obj
        raise ValueError("AS backbone non trouvé")

    def _initialize_routers(self) -> Dict[str, Router]:
        routers = {}

        for pe in self.intent.get("pe_routers", []):
            router = Router(pe, self.backbone_as, "PE")
            router.as_obj.mpls_config = self
            routers[pe["hostname"]] = router

        for p in self.intent.get("p_routers", []):
            router = Router(p, self.backbone_as, "P")
            router.as_obj.mpls_config = self
            routers[p["hostname"]] = router

        for ce in self.intent.get("ce_routers", []):
            as_number = ce["as_number"]
            as_obj = self.as_objects[as_number]
            as_obj.mpls_config = self  # Définir mpls_config sur l'objet AS
            router = Router(ce, as_obj, "CE")
            routers[ce["hostname"]] = router

        return routers

    def _assign_addresses(self):
        """
        Pour chaque lien (c'est-à-dire chaque liste de deux points de terminaison),
        attribue un sous-réseau unique.
        """
        # Attribuer d'abord les adresses Loopback
        for name, router in self.routers.items():
            loopback = router.interfaces.get("Loopback0")
            if loopback:
                if router.as_obj.backbone and hasattr(router.as_obj, 'loopback_iterator'):
                    loopback.ip_address = str(next(router.as_obj.loopback_iterator))
                    loopback.ip_mask = "255.255.255.255"

        # Puis attribuer les interfaces physiques
        for endpoints in self.subnets:
            # Déterminer si le lien connecte un routeur Customer Edge (CE).
            is_pe_ce = any(self.routers[ep["router"]].type == "CE" for ep in endpoints)

            if is_pe_ce:
                # Utiliser le pool d'adresses physiques spécifique à l'AS pour le routeur CE.
                ce_endpoint = next(ep for ep in endpoints if self.routers[ep["router"]].type == "CE")
                as_obj = self.routers[ce_endpoint["router"]].as_obj
                network = next(as_obj.physical_iterator)
            else:
                # Utiliser le pool d'adresses du backbone AS si aucun CE n'est présent.
                network = next(self.backbone_as.physical_iterator)

            # Convertir les hôtes disponibles du réseau en une liste et les attribuer.
            ips = list(network.hosts())
            for i, ep in enumerate(endpoints):
                router = self.routers[ep["router"]]
                iface = router.interfaces.get(ep["interface"])
                if iface is None:
                    raise ValueError(f"L'interface {ep['interface']} n'existe pas sur le router {ep['router']}.")

                iface.ip_address = str(ips[i])
                iface.ip_mask = "255.255.255.0"

                if not is_pe_ce:
                    iface.mpls_enabled = True
                    iface.is_internal = True

    def generate_config(self, router_name: str) -> str:
        router = self.routers[router_name]
        pe_routers = {name: r for name, r in self.routers.items() if r.type == "PE"}
        return "\n".join(router.generate_config_lines(pe_routers))

    def generate_all_configs(self) -> Dict[str, str]:
        return {name: self.generate_config(name) for name in self.routers}

    def recap(self) -> str:
        summary = []
        for name, router in sorted(self.routers.items()):
            summary.append(f"{name} ({router.type}):")
            for iface_name, iface in sorted(router.interfaces.items()):
                summary.append(f" {iface_name}: {iface.ip_address}/{iface.ip_mask}")
        return "\n".join(summary)