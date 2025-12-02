# NAS BGP/MPLS VPN Configuration Generator

## Overview

A Python-based automation system for configuring and managing an MPLS backbone supporting multiple VPN customers in GNS3. Automatically generates complete Cisco router configurations from a JSON intent file, integrating OSPF, LDP, and MP-BGP for MPLS VPN services with VRF and route-target configuration to manage communication between customer sites.

## Repository Structure

```
nas_project/
├── README.md
├── src/
│   ├── main.py                      # GUI application
│   ├── network_config_generator.py  # Configuration generation engine
│   ├── gns3_manager.py              # GNS3 project interface
└── example/                         # Example 
    ├── example.json
    └── example.gns3project
```

## Features

- **Configuration Generation**
  - Automatically generate complete Cisco router startup configurations from JSON intent file
  - Support for PE (Provider Edge), P (Provider), and CE (Customer Edge) routers
  - Automatic IP address allocation from configured ranges
- **MPLS VPN Services**
  - Integrated OSPF and MPLS LDP for routing and label distribution
  - MP-BGP iBGP sessions between PE routers and BGP sessions to customer routers
  - Custom OSPF link costs for traffic engineering
- **Customer Isolation**
  - VRF configuration on PE routers with customizable route targets
  - Route-target based filtering to manage communication between customer sites
- **Deployment & Management**
  - Direct GNS3 integration: generated router configurations are automatically written to router startup files in the GNS3 project folder
  - Network topology recap displaying all subnets and router connections

## Components

### `network_config_generator.py`
Core logic for generating Cisco router configurations:
- Parses JSON intent file with network topology
- Assigns IP addresses from configured ranges
- Generates complete router startup configurations including:
  - VRF definitions with route targets
  - Interface configurations (Loopback0, physical interfaces)
  - OSPF and MPLS LDP for PE/P routers
  - MP-BGP iBGP sessions between PE routers
  - BGP sessions to customer edge routers

### `gns3_manager.py`
Manages interaction with GNS3 Dynamips project directories:
- Scans Dynamips router folders
- Extracts router hostnames from startup configurations
- Writes generated configurations to appropriate router config files

### `main.py`
GUI application (using CustomTkinter) that:
- Allows user to select JSON intent file and GNS3 project directory
- Triggers configuration generation and deployment
- Displays network topology recap after generation
- Provides user feedback on success/errors

## Usage

1. **Prepare Network Intent File**: Create a JSON file defining your network topology (see example/example.json)
2. **Launch Application**: Run `main.py`
3. **Select Files**: 
   - Choose your JSON network intent file
   - Select your GNS3 project directory
4. **Generate**: Click "Generate Configs" button
5. **Deploy**: Configurations are automatically written to router startup-config files
6. **Review**: Network recap window shows subnet details and router connections

## Network Intent JSON Format

The intent file defines your complete network topology and VPN configuration. It must contain the following top-level structures:

### Autonomous Systems (AS)
```json
"as": [
  {
    "as_number": 100,
    "backbone": true,
    "ipv4_ranges": {
      "loopback": "10.0.0.0/24",
      "physical": "10.1.0.0/16"
    }
  }
]
```
- **as_number**: Unique AS identifier (backbone AS used for iBGP)
- **backbone**: Boolean indicating if this is the provider's AS
- **ipv4_ranges**: IP ranges for loopback and physical interfaces (system assigns IPs sequentially)
  - **loopback**: CIDR range for loopback interfaces (any valid CIDR, e.g., `/24`, `/25`)
  - **physical**: CIDR range for physical interfaces (prefix must be `/24` or larger, e.g., `/16`, `/20`) - **important**: the system creates `/24` subnets from this range, so use `/24` or smaller prefix

### Routers
```json
"pe_routers": [
  {
    "hostname": "PE1",
    "interfaces": [
      {"name": "GigabitEthernet0/0"},
      {"name": "GigabitEthernet0/1"}
    ],
    "vrfs": ["VRF_CUSTOMER1"]
  }
],
"p_routers": [...],
"ce_routers": [
  {
    "hostname": "CE1",
    "as_number": 200,
    "private_network": "192.168.1.0/24",
    "interfaces": [{"name": "GigabitEthernet0/0"}]
  }
]
```
- **PE Routers**: Provider Edge routers that connect to customer sites, manage VRFs
  - **hostname**: Router identifier
  - **interfaces**: Physical interfaces connecting to the network
  - **vrfs**: List of VRFs associated with this PE
- **P Routers**: Provider (core) routers for MPLS backbone
  - **hostname**: Router identifier
  - **interfaces**: Physical interfaces connecting to other provider routers
- **CE Routers**: Customer Edge routers with their own AS number
  - **hostname**: Router identifier
  - **as_number**: Customer's unique AS number (different from provider AS)
  - **private_network**: CIDR network representing the customer's internal network behind the CE router (simulates customer site infrastructure)
  - **interfaces**: Physical interface connecting to the provider network

### Subnets (Physical Links)
```json
"subnets": [
  [
    {"router": "PE1", "interface": "GigabitEthernet0/0"},
    {"router": "P1", "interface": "GigabitEthernet0/0"}
  ],
  [
    {"router": "PE1", "interface": "GigabitEthernet0/1"},
    {"router": "CE1", "interface": "GigabitEthernet0/0"}
  ]
]
```
- **Defines physical connections between routers**: Each subnet is an array of 2 router-interface pairs
- **Automatic IP assignment**: IPs are automatically assigned from AS IPv4 ranges
- **Link types**: Can connect PE-P routers (backbone), PE-CE routers (customer connections), or P-P routers

### VRFs (Virtual Routing Domains)
```json
"vrfs": [
  {
    "name": "VRF_CUSTOMER1",
    "rd": "100:1",
    "associated_interfaces": ["GigabitEthernet0/1"],
    "route_targets": {
      "export": ["100:1"],
      "import": ["100:1"]
    }
  }
]
```
- **name**: VRF identifier
- **rd**: Route Distinguisher (ensures unique prefixes)
- **associated_interfaces**: PE interfaces belonging to this VRF
- **route_targets**: Control which routes are imported/exported (enable customer isolation)

### Interface Configuration
```json
"interfaces": [
  {"name": "GigabitEthernet0/0"},
  {"name": "GigabitEthernet0/1", "ospf_cost": 100}
]
```
Each interface can include:
- **name**: Interface name (GigabitEthernet, Loopback, etc.) - required
- **ospf_cost**: Custom OSPF metric (optional, for traffic engineering) - if specified, sets a custom link cost instead of default capacity-based value

> See `example/example.json` for a complete example.
