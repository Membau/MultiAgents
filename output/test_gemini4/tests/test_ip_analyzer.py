from __future__ import annotations

import dataclasses
import ipaddress
from pathlib import Path
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ip_analyzer import (
    AddressScope,
    IPAnalysisError,
    IPVersion,
    analyze_ip,
    classify_address,
    is_private_ip,
    is_public_ip,
    is_valid_ip,
)


class TestIPv4Analysis(unittest.TestCase):
    def test_bare_ipv4_defaults_to_slash_32(self) -> None:
        res = analyze_ip(" 192.168.1.10 ")
        self.assertEqual(res.input_value, " 192.168.1.10 ")
        self.assertEqual(res.version, IPVersion.IPV4)
        self.assertEqual(res.address, ipaddress.IPv4Address("192.168.1.10"))
        self.assertEqual(res.network_address, ipaddress.IPv4Address("192.168.1.10"))
        self.assertEqual(res.broadcast_address, ipaddress.IPv4Address("192.168.1.10"))
        self.assertEqual(res.subnet_mask, ipaddress.IPv4Address("255.255.255.255"))
        self.assertEqual(res.hostmask, ipaddress.IPv4Address("0.0.0.0"))
        self.assertEqual(res.prefix_length, 32)
        self.assertEqual(res.num_addresses, 1)

    def test_cidr_with_host_bits_preserves_host_and_network(self) -> None:
        res = analyze_ip("192.168.1.42/24")
        self.assertEqual(res.address, ipaddress.IPv4Address("192.168.1.42"))
        self.assertEqual(res.network_address, ipaddress.IPv4Address("192.168.1.0"))
        self.assertEqual(res.broadcast_address, ipaddress.IPv4Address("192.168.1.255"))
        self.assertEqual(res.subnet_mask, ipaddress.IPv4Address("255.255.255.0"))
        self.assertEqual(res.hostmask, ipaddress.IPv4Address("0.0.0.255"))
        self.assertEqual(res.prefix_length, 24)
        self.assertEqual(res.num_addresses, 256)

    def test_explicit_netmask_and_prefix_string(self) -> None:
        for mask in ("255.255.0.0", "16"):
            with self.subTest(mask=mask):
                res = analyze_ip("10.20.30.40", subnet_mask=mask)
                self.assertEqual(res.network_address, ipaddress.IPv4Address("10.20.0.0"))
                self.assertEqual(
                    res.broadcast_address, ipaddress.IPv4Address("10.20.255.255")
                )
                self.assertEqual(res.subnet_mask, ipaddress.IPv4Address("255.255.0.0"))
                self.assertEqual(res.prefix_length, 16)
                self.assertEqual(res.num_addresses, 65536)

    def test_boundary_prefixes_slash_0_and_slash_31(self) -> None:
        res0 = analyze_ip("0.0.0.0/0")
        self.assertEqual(res0.prefix_length, 0)
        self.assertEqual(res0.num_addresses, 2**32)
        self.assertEqual(res0.network_address, ipaddress.IPv4Address("0.0.0.0"))
        self.assertEqual(res0.broadcast_address, ipaddress.IPv4Address("255.255.255.255"))

        res31 = analyze_ip("198.51.100.1/31")
        self.assertEqual(res31.prefix_length, 31)
        self.assertEqual(res31.num_addresses, 2)
        self.assertEqual(res31.network_address, ipaddress.IPv4Address("198.51.100.0"))
        self.assertEqual(res31.broadcast_address, ipaddress.IPv4Address("198.51.100.1"))


class TestIPv6Analysis(unittest.TestCase):
    def test_ipv6_cidr_has_no_broadcast_address(self) -> None:
        res = analyze_ip("2001:db8:0:0::1/64")
        self.assertEqual(res.version, IPVersion.IPV6)
        self.assertEqual(res.address, ipaddress.IPv6Address("2001:db8::1"))
        self.assertEqual(res.network_address, ipaddress.IPv6Address("2001:db8::"))
        self.assertIsNone(res.broadcast_address)
        self.assertEqual(res.subnet_mask, ipaddress.IPv6Address("ffff:ffff:ffff:ffff::"))
        self.assertEqual(res.hostmask, ipaddress.IPv6Address("::ffff:ffff:ffff:ffff"))
        self.assertEqual(res.prefix_length, 64)
        self.assertEqual(res.num_addresses, 2**64)

    def test_bare_ipv6_defaults_to_slash_128(self) -> None:
        res = analyze_ip("2001:4860:4860::8888")
        self.assertEqual(res.version, IPVersion.IPV6)
        self.assertEqual(res.prefix_length, 128)
        self.assertEqual(res.num_addresses, 1)
        self.assertIsNone(res.broadcast_address)
        self.assertEqual(
            res.subnet_mask,
            ipaddress.IPv6Address("ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"),
        )

    def test_ipv6_explicit_prefix_mask(self) -> None:
        res = analyze_ip("2001:db8:abcd::42", subnet_mask="48")
        self.assertEqual(res.network_address, ipaddress.IPv6Address("2001:db8:abcd::"))
        self.assertEqual(res.subnet_mask, ipaddress.IPv6Address("ffff:ffff:ffff::"))
        self.assertEqual(res.prefix_length, 48)
        self.assertIsNone(res.broadcast_address)


class TestClassification(unittest.TestCase):
    def test_classify_address_direct(self) -> None:
        self.assertEqual(
            classify_address(ipaddress.IPv4Address("10.1.2.3")),
            (AddressScope.PRIVATE, True, False),
        )
        self.assertEqual(
            classify_address(ipaddress.IPv4Address("8.8.4.4")),
            (AddressScope.PUBLIC, False, True),
        )
        self.assertEqual(
            classify_address(ipaddress.IPv6Address("::ffff:8.8.8.8")),
            (AddressScope.PUBLIC, False, True),
        )

    def test_private_addresses(self) -> None:
        vectors = [
            "10.0.0.1",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.1",
            "fc00::1",
            "fd00::1",
            "::ffff:192.168.1.1",
        ]
        for addr in vectors:
            with self.subTest(addr=addr):
                res = analyze_ip(addr)
                self.assertEqual(res.scope, AddressScope.PRIVATE)
                self.assertTrue(res.is_private)
                self.assertFalse(res.is_public)
                self.assertTrue(is_private_ip(addr))
                self.assertFalse(is_public_ip(addr))

    def test_public_addresses(self) -> None:
        vectors = [
            "8.8.8.8",
            "1.1.1.1",
            "172.32.0.1",  # Outside RFC 1918 172.16.0.0/12
            "192.169.0.1",  # Outside RFC 1918 192.168.0.0/16 and special ranges
            "2001:4860:4860::8888",
            "2606:4700:4700::1111",
        ]
        for addr in vectors:
            with self.subTest(addr=addr):
                res = analyze_ip(addr)
                self.assertEqual(res.scope, AddressScope.PUBLIC)
                self.assertFalse(res.is_private)
                self.assertTrue(res.is_public)
                self.assertTrue(is_public_ip(addr))
                self.assertFalse(is_private_ip(addr))

    def test_special_non_public_addresses(self) -> None:
        cases = [
            ("127.0.0.1", AddressScope.LOOPBACK),
            ("::1", AddressScope.LOOPBACK),
            ("::ffff:127.0.0.1", AddressScope.LOOPBACK),
            ("169.254.1.1", AddressScope.LINK_LOCAL),
            ("fe80::1", AddressScope.LINK_LOCAL),
            ("224.0.0.1", AddressScope.MULTICAST),
            ("ff02::1", AddressScope.MULTICAST),
            ("0.0.0.0", AddressScope.UNSPECIFIED),
            ("::", AddressScope.UNSPECIFIED),
            ("100.64.0.1", AddressScope.RESERVED),  # CGNAT RFC 6598
            ("192.0.0.1", AddressScope.RESERVED),  # IETF Protocol Assignments RFC 6890
            ("192.0.2.1", AddressScope.RESERVED),  # Documentation TEST-NET-1 RFC 5737
            ("2001:db8::1", AddressScope.RESERVED),  # IPv6 Documentation RFC 3849
            ("240.0.0.1", AddressScope.RESERVED),  # Reserved for future use
        ]
        for addr, expected_scope in cases:
            with self.subTest(addr=addr):
                res = analyze_ip(addr)
                self.assertEqual(res.scope, expected_scope)
                self.assertFalse(res.is_private)
                self.assertFalse(res.is_public)


class TestValidationAndImmutability(unittest.TestCase):
    def test_invalid_inputs_raise_ip_analysis_error(self) -> None:
        invalid_vectors: list[tuple[object, object]] = [
            ("", None),
            ("   ", None),
            ("999.1.1.1", None),
            ("192.168.01.1", None),  # Leading zero octet
            ("2001:db8:::1", None),
            ("192.168.1.1/33", None),
            ("2001:db8::1/129", None),
            ("fe80::1%eth0", None),
            ("192.168.1.1", "255.0.255.0"),  # Non-contiguous netmask
            ("192.168.1.1/24", "255.255.0.0"),  # Conflicting CIDR + netmask
            ("192.168.1.1", ""),
            ("192.168.1.1", 24),
            (None, None),
            (12345, None),
        ]
        for addr, mask in invalid_vectors:
            with self.subTest(addr=addr, mask=mask):
                self.assertFalse(is_valid_ip(addr, mask))  # type: ignore[arg-type]
                with self.assertRaises(IPAnalysisError):
                    analyze_ip(addr, mask)  # type: ignore[arg-type]

    def test_ip_analysis_error_is_value_error_subclass(self) -> None:
        self.assertTrue(issubclass(IPAnalysisError, ValueError))
        with self.assertRaises(ValueError):
            analyze_ip("not-an-ip")

    def test_result_is_immutable(self) -> None:
        res = analyze_ip("8.8.8.8")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            res.is_public = False  # type: ignore[misc]

    def test_valid_ip_helper(self) -> None:
        self.assertTrue(is_valid_ip("192.168.1.1"))
        self.assertTrue(is_valid_ip("192.168.1.1", "255.255.255.0"))
        self.assertTrue(is_valid_ip("2001:db8::1/64"))
        self.assertFalse(is_valid_ip("192.168.1.1/24", "255.255.255.0"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
