import ipaddress
from datetime import datetime, timezone
import re


class Interface:
    """Représentation d'une interface réseau sur un routeur."""

    def __init__(self, iface_intent):
        self.name = iface_intent["name"]
        self.ip_address = None
        self.ip_mask = None
        self.mpls_enabled = False
        self.is_internal = False

    def generate_config(self, igp="ospf", router_type=None, as_obj=None):
        """Génère la configuration de l'interface."""
        lines = [f"interface {self.name}"]

        # Configuration IP
        if self.ip_address:
            lines.append(f" ip address {self.ip_address} {self.ip_mask}")

        # Configuration OSPFv2 - Utilisation du numéro d'AS comme area
        if self.ip_address and igp == "ospf" and as_obj:
            # Pour les routeurs PE : uniquement interfaces internes et Loopback0
            # Pour les autres routeurs : toutes les interfaces
            if router_type != "PE" or self.is_internal or self.name == "Loopback0":
                lines.append(f" ip ospf 1 area {as_obj.as_number}")

        # Negotiation auto pour GigabitEthernet
        if "GigabitEthernet" in self.name:
            lines.append(" negotiation auto")

        lines.append("!")
        return lines


class Router:
    """
    Représente un routeur réseau avec ses interfaces et sa configuration.
    """

    def __init__(self, router_intent, as_obj, router_type):
        self.hostname = router_intent["hostname"]
        self.type = router_type
        self.interfaces = {}

        # Création des interfaces
        for iface_intent in router_intent["interfaces"]:
            iface = Interface(iface_intent)
            self.interfaces[iface.name] = iface

        self.as_obj = as_obj  # Référence à l'objet AS

    def generate_config_lines(self, pe_routers=None):
        """
        Génère la configuration complète du routeur sous forme de liste de chaînes.
        """
        lines = self._generate_header()
        lines.extend(self._generate_interfaces())
        lines.extend(self._generate_ospf())

        # Ajouter la configuration BGP si c'est un PE et si les détails des autres PE sont fournis
        if self.type == "PE" and pe_routers:
            lines.extend(self._generate_bgp(pe_routers))

        lines.extend(self._generate_footer())
        return lines

    def _generate_header(self):
        """
        Génère l'en-tête de la configuration du routeur.
        """
        now_str = datetime.now(timezone.utc).strftime('%H:%M:%S UTC %a %b %d %Y')
        return [
            "!",
            f"! Last configuration change at {now_str}",
            "!",
            "version 15.2",
            "service timestamps debug datetime msec",
            "service timestamps log datetime msec",
            "!",
            f"hostname {self.hostname}",
            "!",
            "boot-start-marker",
            "boot-end-marker",
            "!",
            "no aaa new-model",
            "no ip icmp rate-limit unreachable",
            "ip cef",
            "!",
            "no ip domain lookup",
            "no ipv6 cef",
            "!",
            "mpls label protocol ldp",
            "multilink bundle-name authenticated",
            "!",
            "ip tcp synwait-time 5",
            "!",
        ]

    def _generate_interfaces(self):
        """
        Génère la section de configuration des interfaces.
        """
        interface_lines = []

        # Passage du type de routeur et de l'AS à la méthode generate_config
        for name, iface in sorted(self.interfaces.items()):
            interface_lines.extend(iface.generate_config(self.as_obj.igp, self.type, self.as_obj))

        return interface_lines

    def _generate_unique_router_id(self):
        """
        Génère un router-ID unique pour le routeur.
        """
        # Utiliser l'adresse IP de Loopback0
        return self.interfaces["Loopback0"].ip_address

    def _generate_ospf(self):
        """
        Génère la configuration OSPF.
        """
        if self.as_obj.igp != "ospf":
            return []

        # Génération d'un router-ID unique
        router_id = self._generate_unique_router_id()

        return [
            "router ospf 1",
            f" router-id {router_id}",
            " mpls ldp autoconfig",
            "!"
        ]

    def _generate_bgp(self, pe_routers):
        """
        Génère la configuration BGP pour les routeurs PE.
        """
        # Vérifier si c'est un routeur PE
        if self.type != "PE":
            return []

        # Récupérer le numéro d'AS
        as_number = self.as_obj.as_number

        # Utiliser l'adresse Loopback0 comme router-id BGP
        router_id = self.interfaces["Loopback0"].ip_address

        lines = [
            f"router bgp {as_number}",
            f" bgp router-id {router_id}",
            " bgp log-neighbor-changes"
        ]

        # Ajouter les neighbors (autres PE)
        for pe_name, pe_router in pe_routers.items():
            # Ne pas ajouter le routeur lui-même comme neighbor
            if pe_name != self.hostname:
                neighbor_ip = pe_router.interfaces["Loopback0"].ip_address
                lines.append(f" neighbor {neighbor_ip} remote-as {as_number}")
                lines.append(f" neighbor {neighbor_ip} update-source Loopback0")

        # Configuration address-family IPv4
        lines.append(" !")
        lines.append(" address-family ipv4")
        for pe_name, pe_router in pe_routers.items():
            if pe_name != self.hostname:
                neighbor_ip = pe_router.interfaces["Loopback0"].ip_address
                lines.append(f"  neighbor {neighbor_ip} activate")
        lines.append(" exit-address-family")
        lines.append("!")

        return lines

    def _generate_footer(self):
        """
        Génère le pied de page de la configuration du routeur.
        """
        return [
            "ip forward-protocol nd",
            "!",
            "no ip http server",
            "no ip http secure-server",
            "!",
            "control-plane",
            "!",
            "line con 0",
            " exec-timeout 0 0",
            " privilege level 15",
            " logging synchronous",
            " stopbits 1",
            "line aux 0",
            " exec-timeout 0 0",
            " privilege level 15",
            " logging synchronous",
            " stopbits 1",
            "line vty 0 4",
            " login",
            "!",
            "end"
        ]


class AS:
    """Représentation d'un Système Autonome."""

    def __init__(self, as_intent):
        self.as_number = as_intent["as_number"]
        self.igp = "ospf"  # Par défaut

        # Initialisation des plages d'adressage
        self.loopback_iterator = ipaddress.IPv4Network(as_intent["ipv4_ranges"]["loopback"]).hosts()
        self.physical_iterator = ipaddress.IPv4Network(as_intent["ipv4_ranges"]["physical"]).subnets(new_prefix=24)


class MPLSConfig:
    """Générateur de configuration pour un réseau MPLS."""

    def __init__(self, intent):
        self.intent = intent
        self.backbone_as = self._initialize_backbone()
        self.routers = self._initialize_routers()
        self.subnets = self._initialize_subnets()

        # Allocation des adresses
        self._assign_loopbacks_addr()
        self._assign_physical_addr()

    def _initialize_backbone(self):
        """Initialise l'AS backbone."""
        return AS(self.intent["backbone"])

    def _initialize_routers(self):
        """Initialise les objets Router."""
        routers = {}

        # Création des routeurs PE
        for pe_intent in self.intent["pe_routers"]:
            router = Router(pe_intent, self.backbone_as, "PE")
            routers[router.hostname] = router

        # Création des routeurs P
        for p_intent in self.intent["p_routers"]:
            router = Router(p_intent, self.backbone_as, "P")
            routers[router.hostname] = router

        return routers

    def _initialize_subnets(self):
        """Initialise les sous-réseaux."""
        return self.intent["subnets"]

    def _assign_loopbacks_addr(self):
        """Attribue des adresses loopback aux routeurs."""
        for router in self.routers.values():
            if "Loopback0" in router.interfaces:
                try:
                    ip = next(self.backbone_as.loopback_iterator)
                    router.interfaces["Loopback0"].ip_address = f"{ip}"
                    router.interfaces["Loopback0"].ip_mask = "255.255.0.0"
                except StopIteration:
                    raise ValueError("Pas assez d'adresses loopback disponibles")

    def _assign_physical_addr(self):
        """Attribue des adresses IP aux interfaces physiques."""
        for subnet in self.subnets:
            if not subnet or len(subnet) != 2:
                continue

            # Allocation d'un sous-réseau /24
            try:
                assigned_network = next(self.backbone_as.physical_iterator)
                hosts_iterator = assigned_network.hosts()

                # Attribution des adresses aux deux extrémités
                r1_name = subnet[0]["router"]
                i1_name = subnet[0]["interface"]

                r2_name = subnet[1]["router"]
                i2_name = subnet[1]["interface"]

                # Assignation des adresses IP
                self.routers[r1_name].interfaces[i1_name].ip_address = f"{next(hosts_iterator)}"
                self.routers[r1_name].interfaces[i1_name].ip_mask = "255.255.255.0"

                self.routers[r2_name].interfaces[i2_name].ip_address = f"{next(hosts_iterator)}"
                self.routers[r2_name].interfaces[i2_name].ip_mask = "255.255.255.0"

                # Marquage des interfaces comme internes
                self.routers[r1_name].interfaces[i1_name].is_internal = True
                self.routers[r2_name].interfaces[i2_name].is_internal = True

                # Activation MPLS sur les interfaces P et PE
                if self.routers[r1_name].type in ["P", "PE"]:
                    self.routers[r1_name].interfaces[i1_name].mpls_enabled = True

                if self.routers[r2_name].type in ["P", "PE"]:
                    self.routers[r2_name].interfaces[i2_name].mpls_enabled = True

            except StopIteration:
                raise ValueError("Pas assez de sous-réseaux disponibles")

    def generate_config(self, router_name):
        """Génère la configuration d'un routeur spécifique."""
        if router_name not in self.routers:
            raise ValueError(f"Routeur {router_name} non trouvé")

        router = self.routers[router_name]

        # Créer un dictionnaire de routeurs PE pour la configuration BGP
        pe_routers = {name: r for name, r in self.routers.items() if r.type == "PE"}

        return "\n".join(router.generate_config_lines(pe_routers))

    def generate_all_configs(self):
        """Génère les configurations pour tous les routeurs."""
        configs = {}

        # Créer un dictionnaire de routeurs PE pour la configuration BGP
        pe_routers = {name: r for name, r in self.routers.items() if r.type == "PE"}

        for name, router in self.routers.items():
            configs[name] = "\n".join(router.generate_config_lines(pe_routers))
        return configs

    def recap(self):
        """
        Génère un récapitulatif du réseau, montrant toutes les adresses d'interface pour chaque routeur.
        """
        recap_lines = ["Récapitulatif du réseau MPLS:", "=" * 50]

        # Parcourir tous les routeurs
        for router_name, router in sorted(self.routers.items()):
            recap_lines.append(f"\nRouteur: {router_name} (Type: {router.type})")
            recap_lines.append("-" * 50)

            # Parcourir les interfaces de chaque routeur
            for iface_name, iface in sorted(router.interfaces.items()):
                ip_info = f"{iface.ip_address}/{iface.ip_mask}" if iface.ip_address else "Pas d'adresse IP"

                recap_lines.append(f"  Interface: {iface_name}")
                recap_lines.append(f"    Adresse IP: {ip_info}")

        return "\n".join(recap_lines)

