from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
import ipaddress
from ipaddress import (
    IPv4Address,
    IPv4Interface,
    IPv4Network,
    IPv6Address,
    IPv6Interface,
    IPv6Network,
)

IPAddress = IPv4Address | IPv6Address
IPInterface = IPv4Interface | IPv6Interface

# Explicit RFC 1918 (IPv4) and RFC 4193 (IPv6) private ranges ensure
# consistent classification across Python 3.10+ ipaddress patch versions.
_IPV4_PRIVATE_NETWORKS: tuple[IPv4Network, ...] = (
    IPv4Network("10.0.0.0/8"),
    IPv4Network("172.16.0.0/12"),
    IPv4Network("192.168.0.0/16"),
)
_IPV6_PRIVATE_NETWORK: IPv6Network = IPv6Network("fc00::/7")


class IPVersion(IntEnum):
    IPV4 = 4
    IPV6 = 6


class AddressScope(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    LOOPBACK = "loopback"
    LINK_LOCAL = "link_local"
    MULTICAST = "multicast"
    UNSPECIFIED = "unspecified"
    RESERVED = "reserved"


class IPAnalysisError(ValueError):
    """Domain exception raised when IP input or subnet mask is invalid."""


@dataclass(frozen=True)
class IPAnalysisResult:
    input_value: str
    address: IPAddress
    version: IPVersion
    network_address: IPAddress
    broadcast_address: IPv4Address | None
    subnet_mask: IPAddress
    hostmask: IPAddress
    prefix_length: int
    num_addresses: int
    is_private: bool
    is_public: bool
    scope: AddressScope


def _validate_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise IPAnalysisError(
            f"{field_name} must be a str, got {type(value).__name__}."
        )
    stripped = value.strip()
    if not stripped:
        raise IPAnalysisError(f"{field_name} must not be empty or whitespace.")
    return stripped


def parse_ip_input(address_input: str, subnet_mask: str | None = None) -> IPInterface:
    """Parse an IP/CIDR string (with optional explicit subnet mask) into an ip_interface."""
    raw_addr = _validate_non_empty_str(address_input, "address_input")

    if "%" in raw_addr:
        raise IPAnalysisError(
            f"IPv6 zone IDs are not supported in subnet analysis: {raw_addr!r}"
        )

    if subnet_mask is not None:
        raw_mask = _validate_non_empty_str(subnet_mask, "subnet_mask")
        if "/" in raw_addr:
            raise IPAnalysisError(
                "Conflicting mask specification: provide either CIDR notation or subnet_mask, not both."
            )
        candidate = f"{raw_addr}/{raw_mask}"
    else:
        candidate = raw_addr

    try:
        return ipaddress.ip_interface(candidate)
    except ValueError as exc:
        raise IPAnalysisError(
            f"Invalid IP address or subnet mask: {candidate!r}"
        ) from exc


def _resolve_effective_address(ip: IPAddress) -> IPAddress:
    """Unwrap IPv4-mapped IPv6 addresses (::ffff:x.x.x.x) for accurate scope checks."""
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_rfc_private(ip: IPAddress) -> bool:
    """Return True for RFC 1918 (IPv4) and RFC 4193 ULA (IPv6) private ranges."""
    if isinstance(ip, IPv4Address):
        return any(ip in net for net in _IPV4_PRIVATE_NETWORKS)
    return ip in _IPV6_PRIVATE_NETWORK


def classify_address(ip: IPAddress) -> tuple[AddressScope, bool, bool]:
    """Classify an IP address into (scope, is_private, is_public)."""
    target = _resolve_effective_address(ip)

    if target.is_unspecified:
        return AddressScope.UNSPECIFIED, False, False
    if target.is_loopback:
        return AddressScope.LOOPBACK, False, False
    if target.is_link_local:
        return AddressScope.LINK_LOCAL, False, False
    if target.is_multicast:
        return AddressScope.MULTICAST, False, False
    if _is_rfc_private(target):
        return AddressScope.PRIVATE, True, False
    if target.is_reserved or not target.is_global:
        return AddressScope.RESERVED, False, False

    return AddressScope.PUBLIC, False, True


def analyze_ip(address_input: str, subnet_mask: str | None = None) -> IPAnalysisResult:
    """Validate and analyze an IPv4/IPv6 address with optional CIDR or subnet mask."""
    interface = parse_ip_input(address_input, subnet_mask=subnet_mask)
    network = interface.network
    address = interface.ip
    version = IPVersion.IPV4 if address.version == 4 else IPVersion.IPV6

    # RFC 4291: IPv6 has no broadcast address.
    broadcast_address: IPv4Address | None = (
        network.broadcast_address if isinstance(network, IPv4Network) else None
    )

    scope, is_private, is_public = classify_address(address)

    return IPAnalysisResult(
        input_value=address_input,
        address=address,
        version=version,
        network_address=network.network_address,
        broadcast_address=broadcast_address,
        subnet_mask=network.netmask,
        hostmask=network.hostmask,
        prefix_length=network.prefixlen,
        num_addresses=network.num_addresses,
        is_private=is_private,
        is_public=is_public,
        scope=scope,
    )


def is_valid_ip(address_input: str, subnet_mask: str | None = None) -> bool:
    """Return True if address_input (and optional subnet_mask) parses cleanly."""
    try:
        parse_ip_input(address_input, subnet_mask=subnet_mask)
        return True
    except IPAnalysisError:
        return False


def is_private_ip(address_input: str) -> bool:
    """Return True if the given IP/CIDR belongs to a private address range."""
    return analyze_ip(address_input).is_private


def is_public_ip(address_input: str) -> bool:
    """Return True if the given IP/CIDR belongs to a globally routable public range."""
    return analyze_ip(address_input).is_public
