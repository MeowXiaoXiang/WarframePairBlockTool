import unittest

from src.controller.firewall import FirewallController, RuleCreationError


class RecordingFirewallController(FirewallController):
    def __init__(self):
        super().__init__()
        self.commands = []

    def run_command(self, command):
        self.commands.append(command)
        return 0, "", ""


class FirewallPortTests(unittest.TestCase):
    def test_each_ui_pair_creates_a_two_port_rule(self):
        controller = RecordingFirewallController()
        pairs = ((4950, 4955), (4960, 4965), (4970, 4975),
                 (4980, 4985), (4990, 4995), (3074, 3080))

        for first, second in pairs:
            with self.subTest(ports=(first, second)):
                controller.create_rule(str(first), str(second))
                self.assertIn(f"localport={first},{second} ", controller.commands[-1])
                self.assertIn("protocol=UDP dir=out", controller.commands[-1])
                self.assertIn("action=block", controller.commands[-1])

    def test_invalid_ports_never_reach_netsh(self):
        controller = RecordingFirewallController()
        for ports in (("4950-4955", "4955"), ("4950&other", "4955"),
                      ("0", "4955"), ("65536", "4955"),
                      ("4950", "4950"), ("04950", "4950")):
            with self.subTest(ports=ports):
                with self.assertRaises(RuleCreationError):
                    controller.create_rule(*ports)
        self.assertEqual(controller.commands, [])


if __name__ == "__main__":
    unittest.main()
