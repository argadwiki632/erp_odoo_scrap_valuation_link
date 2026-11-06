from types import SimpleNamespace
from unittest.mock import patch

from lxml import etree

from odoo.addons.stock_account.tests.test_stockvaluation import TestStockValuationBase
from odoo.exceptions import AccessError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestScrapValuations(TestStockValuationBase):
    def _scrap(self):
        return self.env["stock.scrap"].create({
            "product_id": self.product1.id, "scrap_qty": 1,
            "location_id": self.stock_location.id,
        })

    def test_action_only_returns_this_scrap_layers(self):
        self.product1.standard_price = 20
        receipt = self._make_in_move(self.product1, 5)
        scrap = self._scrap()
        scrap.action_validate()
        other = self._scrap()
        other.action_validate()
        action = scrap.action_view_stock_valuation_layers()
        self.assertEqual(action["res_model"], "stock.valuation.layer")
        self.assertTrue(action["context"]["no_at_date"])
        self.assertIn("pivot_measures", action["context"])
        layers = self.env["stock.valuation.layer"].search(action["domain"])
        self.assertEqual(layers, scrap.move_ids.stock_valuation_layer_ids)
        self.assertFalse(layers & (receipt | other.move_ids).stock_valuation_layer_ids)
        adjustment = self.env["stock.valuation.layer"].create({
            "product_id": self.product1.id, "company_id": self.env.company.id,
            "stock_move_id": scrap.move_ids.id, "value": -5,
            "quantity": 0, "description": "Later scrap adjustment",
        })
        self.assertIn(adjustment, self.env["stock.valuation.layer"].search(action["domain"]))

    def test_draft_action_and_native_access_rules(self):
        scrap = self._scrap()
        action = scrap.action_view_stock_valuation_layers()
        self.assertFalse(self.env["stock.valuation.layer"].search(action["domain"]))
        action = scrap.with_user(self.inventory_user).action_view_stock_valuation_layers()
        with self.assertRaises(AccessError):
            self.env["stock.valuation.layer"].with_user(self.inventory_user).search(action["domain"])

    def test_button_uses_native_debug_group(self):
        view = self.env.ref("arga_scrap_valuation.stock_scrap_form")
        button = etree.fromstring(view.arch_db).xpath("//button")[0]
        self.assertEqual(button.get("groups"), "base.group_no_one")
        self.assertEqual(button.get("invisible"), "state != 'done'")
        self.assertEqual(button.get("name"), "action_view_stock_valuation_layers")

    def test_button_visibility_follows_debug_mode(self):
        self.env.user.groups_id |= self.env.ref("base.group_no_one")
        model = self.env["stock.scrap"]
        view_id = self.env.ref("stock.stock_scrap_form_view").id
        request = SimpleNamespace(session=SimpleNamespace(debug=False))
        with patch("odoo.addons.base.models.ir_ui_view.request", request):
            arch = etree.fromstring(model.get_view(view_id, "form")["arch"])
            self.assertFalse(arch.xpath("//button[@name='action_view_stock_valuation_layers']"))
            request.session.debug = True
            arch = etree.fromstring(model.get_view(view_id, "form")["arch"])
            self.assertTrue(arch.xpath("//button[@name='action_view_stock_valuation_layers']"))
