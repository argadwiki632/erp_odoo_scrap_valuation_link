from ast import literal_eval
from types import SimpleNamespace
from unittest.mock import patch

from lxml import etree

from odoo.addons.stock_account.tests.test_stockvaluation import _create_accounting_data
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestScrapValuations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.product1 = cls.env["product.product"].create({
            "name": "Scrap Test Product", "type": "product",
        })
        input_account, output_account, valuation_account, expense_account, journal = _create_accounting_data(cls.env)
        cls.product1.categ_id.write({
            "property_valuation": "real_time",
            "property_stock_account_input_categ_id": input_account.id,
            "property_stock_account_output_categ_id": output_account.id,
            "property_stock_valuation_account_id": valuation_account.id,
            "property_stock_journal": journal.id,
        })
        cls.product1.property_account_expense_id = expense_account
        cls.inventory_user = cls.env["res.users"].create({
            "name": "Scrap Inventory User", "login": "scrap_inventory",
            "groups_id": [(6, 0, [cls.env.ref("stock.group_stock_user").id])],
        })

    def _make_in_move(self, product, quantity):
        move = self.env["stock.move"].create({
            "name": "Receipt for scrap", "product_id": product.id,
            "product_uom": product.uom_id.id, "product_uom_qty": quantity,
            "price_unit": product.standard_price,
            "location_id": self.env.ref("stock.stock_location_suppliers").id,
            "location_dest_id": self.stock_location.id,
        })
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.qty_done = quantity
        move._action_done()
        return move

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
        native_action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")
        for key, value in literal_eval(native_action["context"]).items():
            self.assertEqual(action["context"][key], value)
        layers = self.env["stock.valuation.layer"].search(action["domain"])
        self.assertEqual(layers, scrap.move_id.stock_valuation_layer_ids)
        self.assertFalse(layers & (receipt | other.move_id).stock_valuation_layer_ids)
        adjustment = self.env["stock.valuation.layer"].create({
            "product_id": self.product1.id, "company_id": self.env.company.id,
            "stock_move_id": scrap.move_id.id, "value": -5,
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
        self.assertEqual(button.get("attrs"), "{'invisible': [('state', '!=', 'done')]}")
        self.assertEqual(button.get("name"), "action_view_stock_valuation_layers")

    def test_button_visibility_follows_debug_mode(self):
        self.env.user.groups_id |= self.env.ref("base.group_no_one")
        model = self.env["stock.scrap"]
        view_id = self.env.ref("stock.stock_scrap_form_view").id
        request = SimpleNamespace(session=SimpleNamespace(debug=False))
        with patch("odoo.http.request", request):
            arch = etree.fromstring(model.get_view(view_id, "form")["arch"])
            self.assertFalse(arch.xpath("//button[@name='action_view_stock_valuation_layers']"))
            request.session.debug = True
            arch = etree.fromstring(model.get_view(view_id, "form")["arch"])
            self.assertTrue(arch.xpath("//button[@name='action_view_stock_valuation_layers']"))
