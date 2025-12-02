# Example Network Configuration

This directory contains an example MPLS VPN network configuration demonstrating multi-customer VPN isolation using route targets and VRFs.

## Network Topology

The example demonstrates a 4-PE router backbone with 6 customer edge routers (CE) organized in 3 distinct VPN communities:

- **CLIENT1 & CLIENT2**: Interconnected VPN pair
- **CLIENT3 & CLIENT6**: Interconnected VPN pair  
- **CLIENT4 & CLIENT5**: Interconnected VPN pair

## VRF and Route Target Communication Summary

| VRF Name | PE Router | Exports | Imports | CE Router / Communication |
|----------|-----------|---------|---------|---------------------------|
| CLIENT1 | PE1 | `65000:1` | `65000:2` | CE1 ↔ CE2 |
| CLIENT2 | PE2 | `65000:2` | `65000:1` | CE2 ↔ CE1 |
| CLIENT3 | PE3 | `65000:3` | `65000:6` | CE3 ↔ CE6 |
| CLIENT6 | PE4 | `65000:6` | `65000:3` | CE6 ↔ CE3 |
| CLIENT5 | PE3 | `65000:5` | `65000:4` | CE5 ↔ CE4 |
| CLIENT4 | PE4 | `65000:4` | `65000:5` | CE4 ↔ CE5 |

**Key Observation**: Only CE pairs CE1↔CE2, CE3↔CE6, and CE5↔CE4 can communicate. All other combinations are isolated because there is no mutual import/export of route targets between them.

## Validation Tests

### 1. Basic Connectivity
Test ping from CE to remote CE (e.g., from CE1 to 10.2.2.2):
```
ping 10.2.2.2
```

### 2. MPLS Path Verification
Trace the MPLS path (e.g., from CE1 to 10.2.2.2):
```
traceroute 10.2.2.2
```

### 3. Routing Table Verification
Verify routes are present in each PE VRF:
```
show ip route vrf [CLIENTX]
```
- Expected: Customer routes should appear for clients with matching route targets
- Absent: Routes should not appear for isolated VPNs

### 4. VPNv4 Route Exchange
Verify VPNv4 route distribution between PEs:
```
show bgp vpnv4 unicast all
```
- Confirms MP-BGP sessions are working
- Shows which routes are being advertised between PEs

### 5. MPLS Label Verification
Verify label imposition and distribution:
```
show mpls forwarding-table
```
- Confirms LDP labels are assigned
- Verifies MPLS forwarding paths

### 6. Blocked Communication Test
Attempt communication between isolated VPNs (should fail):
- Ping from CE1 to CE3 (different VPN pair)
- Ping from CE4 to CE1 (different VPN pair)
- Expected result: Unreachable (no route)

## How to Use

1. Open the GNS3 project file (`example.gns3project`)
2. Ensure routers are running (start all nodes)
3. Generate fresh configurations using the main application with `example.json`
4. Run validation tests from router CLIs (telnet/SSH to routers)
5. Verify results match expected communication patterns

## Conclusion

This example demonstrates how MPLS VPN services can isolate customer traffic through intelligent use of VRFs and route targets. Only customers within the same VPN community can communicate, while the provider backbone remains transparent to customers and supports any-to-any customer connectivity patterns through BGP route target filtering.
