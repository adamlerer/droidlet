from agents.craftassist.tests.base_craftassist_test_case import BaseCraftassistTestCase
from droidlet.interpreter.craftassist.default_behaviors import build_random_shape


class TestDefaultBehavior(BaseCraftassistTestCase):
    def setUp(self):
        super().setUp()
        schematic = build_random_shape(self.agent)
        self.assertTrue(len(schematic) > 0)
