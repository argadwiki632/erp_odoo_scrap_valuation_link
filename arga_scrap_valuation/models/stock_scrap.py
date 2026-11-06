from ast import literal_eval

from odoo import models


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    def action_view_stock_valuation_layers(self):
        self.ensure_one()
        self.check_access_rights("read")
        self.check_access_rule("read")
        action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")
        action["domain"] = [("stock_move_id", "in", self.move_ids.ids)]
        action["context"] = {
            **literal_eval(action["context"]), **self.env.context, "no_at_date": True,
        }
        return action
