
## floci

| Tài nguyên | Trường | Kết quả | Ghi chú |
|---|---|---|---|
| VPC | `VpcId` | có |  |
| VPC | `CidrBlock` | có | 10.0.0.0/16 |
| VPC | `Tags` | có |  |
| AZ | `ZoneName` | có | 3 AZ |
| AZ | `ZoneId` | có |  |
| Subnet | `SubnetId` | có | 4 trong VPC |
| Subnet | `VpcId` | có |  |
| Subnet | `CidrBlock` | có |  |
| Subnet | `AvailabilityZone` | có |  |
| Subnet | `MapPublicIpOnLaunch` | có | [True, True, False, False] |
| Internet Gateway | `InternetGatewayId` | có |  |
| Internet Gateway | `Attachments[].VpcId` | có |  |
| Internet Gateway | `Attachments[].State` | có | available |
| NAT Gateway | `NatGatewayId` | có |  |
| NAT Gateway | `SubnetId` | có |  |
| NAT Gateway | `VpcId` | có |  |
| NAT Gateway | `State` | có | available |
| NAT Gateway | `NatGatewayAddresses` | có | 54.67.149.169 |
| Route Table | `RouteTableId` | có | 3 trong VPC |
| Route Table | `VpcId` | có |  |
| Route Table | `Associations[].SubnetId` | có |  |
| Route Table | `Associations[].Main` | có | 1 main |
| Route Table | `Routes[].DestinationCidrBlock` | có | có route local |
| Route Table | `Routes[].GatewayId` | có |  |
| Route Table | `Routes[].NatGatewayId` | có |  |
| Security Group | `GroupId` | có | 2 trong VPC |
| Security Group | `VpcId` | có |  |
| Security Group | `IpPermissions` | có |  |
| Security Group | `IpPermissionsEgress` | có |  |
| Key Pair | `KeyName` | có |  |
| Key Pair | `KeyPairId` | có |  |
| Instance | `InstanceId` | có |  |
| Instance | `State.Name` | có | running |
| Instance | `SubnetId` | có |  |
| Instance | `VpcId` | có |  |
| Instance | `SecurityGroups` | có |  |
| Instance | `PublicIpAddress` | có | 127.0.0.1 |
| Instance | `PrivateIpAddress` | sai | 10.240.0.11 |
| Instance | `KeyName` | có |  |

## floci-default-config

| Tài nguyên | Trường | Kết quả | Ghi chú |
|---|---|---|---|
| VPC | `VpcId` | có |  |
| VPC | `CidrBlock` | có | 10.0.0.0/16 |
| VPC | `Tags` | có |  |
| AZ | `ZoneName` | có | 3 AZ |
| AZ | `ZoneId` | có |  |
| Subnet | `SubnetId` | có | 4 trong VPC |
| Subnet | `VpcId` | có |  |
| Subnet | `CidrBlock` | có |  |
| Subnet | `AvailabilityZone` | có |  |
| Subnet | `MapPublicIpOnLaunch` | có | [True, True, False, False] |
| Internet Gateway | `InternetGatewayId` | có |  |
| Internet Gateway | `Attachments[].VpcId` | có |  |
| Internet Gateway | `Attachments[].State` | có | available |
| NAT Gateway | `NatGatewayId` | có |  |
| NAT Gateway | `SubnetId` | có |  |
| NAT Gateway | `VpcId` | có |  |
| NAT Gateway | `State` | có | available |
| NAT Gateway | `NatGatewayAddresses` | có | 54.17.139.34 |
| Route Table | `RouteTableId` | có | 3 trong VPC |
| Route Table | `VpcId` | có |  |
| Route Table | `Associations[].SubnetId` | có |  |
| Route Table | `Associations[].Main` | có | 1 main |
| Route Table | `Routes[].DestinationCidrBlock` | có | có route local |
| Route Table | `Routes[].GatewayId` | có |  |
| Route Table | `Routes[].NatGatewayId` | có |  |
| Security Group | `GroupId` | có | 2 trong VPC |
| Security Group | `VpcId` | có |  |
| Security Group | `IpPermissions` | có |  |
| Security Group | `IpPermissionsEgress` | có |  |
| Key Pair | `KeyName` | có |  |
| Key Pair | `KeyPairId` | có |  |
| Instance | `InstanceId` | có |  |
| Instance | `State.Name` | có | running |
| Instance | `SubnetId` | có |  |
| Instance | `VpcId` | có |  |
| Instance | `SecurityGroups` | có |  |
| Instance | `PublicIpAddress` | có | 127.0.0.1 |
| Instance | `PrivateIpAddress` | sai | 10.240.0.11 |
| Instance | `KeyName` | có |  |

## ministack

| Tài nguyên | Trường | Kết quả | Ghi chú |
|---|---|---|---|
| VPC | `VpcId` | có |  |
| VPC | `CidrBlock` | có | 10.0.0.0/16 |
| VPC | `Tags` | có |  |
| AZ | `ZoneName` | có | 3 AZ |
| AZ | `ZoneId` | có |  |
| Subnet | `SubnetId` | có | 4 trong VPC |
| Subnet | `VpcId` | có |  |
| Subnet | `CidrBlock` | có |  |
| Subnet | `AvailabilityZone` | có |  |
| Subnet | `MapPublicIpOnLaunch` | có | [True, True, False, False] |
| Internet Gateway | `InternetGatewayId` | có |  |
| Internet Gateway | `Attachments[].VpcId` | có |  |
| Internet Gateway | `Attachments[].State` | có | available |
| NAT Gateway | `NatGatewayId` | có |  |
| NAT Gateway | `SubnetId` | có |  |
| NAT Gateway | `VpcId` | có |  |
| NAT Gateway | `State` | có | available |
| NAT Gateway | `NatGatewayAddresses` | thiếu |  |
| Route Table | `RouteTableId` | có | 3 trong VPC |
| Route Table | `VpcId` | có |  |
| Route Table | `Associations[].SubnetId` | có |  |
| Route Table | `Associations[].Main` | có | 1 main |
| Route Table | `Routes[].DestinationCidrBlock` | có | có route local |
| Route Table | `Routes[].GatewayId` | có |  |
| Route Table | `Routes[].NatGatewayId` | có |  |
| Security Group | `GroupId` | có | 2 trong VPC |
| Security Group | `VpcId` | có |  |
| Security Group | `IpPermissions` | có |  |
| Security Group | `IpPermissionsEgress` | có |  |
| Key Pair | `KeyName` | có |  |
| Key Pair | `KeyPairId` | có |  |
| Instance | `InstanceId` | có |  |
| Instance | `State.Name` | có | running |
| Instance | `SubnetId` | có |  |
| Instance | `VpcId` | có |  |
| Instance | `SecurityGroups` | có |  |
| Instance | `PublicIpAddress` | có | 54.226.173.231 |
| Instance | `PrivateIpAddress` | sai | 10.0.146.90 |
| Instance | `KeyName` | có |  |

## Tổng hợp

| Tài nguyên | floci | floci-default-config | ministack |
|---|---|---|---|
| VPC | 3/3 có | 3/3 có | 3/3 có |
| AZ | 2/2 có | 2/2 có | 2/2 có |
| Subnet | 5/5 có | 5/5 có | 5/5 có |
| Internet Gateway | 3/3 có | 3/3 có | 3/3 có |
| NAT Gateway | 5/5 có | 5/5 có | 4/5 có (NatGatewayAddresses thiếu) |
| Route Table | 7/7 có | 7/7 có | 7/7 có |
| Security Group | 4/4 có | 4/4 có | 4/4 có |
| Key Pair | 2/2 có | 2/2 có | 2/2 có |
| Instance | 7/8 có (PrivateIpAddress sai) | 7/8 có (PrivateIpAddress sai) | 7/8 có (PrivateIpAddress sai) |
