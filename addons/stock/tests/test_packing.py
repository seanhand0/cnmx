# -*- coding: utf-8 -*-
# Part of Cnmx. See LICENSE file for full copyright and licensing details.

from odoo.tests import Form
from odoo.tests.common import SavepointCase
from odoo.tools import float_round
from odoo.exceptions import UserError


class TestPacking(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super(TestPacking, cls).setUpClass()
        cls.stock_location = cls.env.ref('stock.stock_location_stock')
        cls.warehouse = cls.env['stock.warehouse'].search([('lot_stock_id', '=', cls.stock_location.id)], limit=1)
        cls.warehouse.write({'delivery_steps': 'pick_pack_ship'})
        cls.pack_location = cls.warehouse.wh_pack_stock_loc_id
        cls.ship_location = cls.warehouse.wh_output_stock_loc_id
        cls.customer_location = cls.env.ref('stock.stock_location_customers')

        cls.productA = cls.env['product.product'].create({'name': 'Product A', 'type': 'product'})
        cls.productB = cls.env['product.product'].create({'name': 'Product B', 'type': 'product'})

    def test_put_in_pack(self):
        """ In a pick pack ship scenario, create two packs in pick and check that
        they are correctly recognised and handled by the pack and ship picking.
        Along this test, we'll use action_toggle_processed to process a pack
        from the entire_package_ids one2many and we'll directly fill the move
        lines, the latter is the behavior when the user did not enable the display
        of entire packs on the picking type.
        """
        self.env['stock.quant']._update_available_quantity(self.productA, self.stock_location, 20.0)
        self.env['stock.quant']._update_available_quantity(self.productB, self.stock_location, 20.0)
        ship_move_a = self.env['stock.move'].create({
            'name': 'The ship move',
            'product_id': self.productA.id,
            'product_uom_qty': 5.0,
            'product_uom': self.productA.uom_id.id,
            'location_id': self.ship_location.id,
            'location_dest_id': self.customer_location.id,
            'warehouse_id': self.warehouse.id,
            'picking_type_id': self.warehouse.out_type_id.id,
            'procure_method': 'make_to_order',
            'state': 'draft',
        })
        ship_move_b = self.env['stock.move'].create({
            'name': 'The ship move',
            'product_id': self.productB.id,
            'product_uom_qty': 5.0,
            'product_uom': self.productB.uom_id.id,
            'location_id': self.ship_location.id,
            'location_dest_id': self.customer_location.id,
            'warehouse_id': self.warehouse.id,
            'picking_type_id': self.warehouse.out_type_id.id,
            'procure_method': 'make_to_order',
            'state': 'draft',
        })
        ship_move_a._assign_picking()
        ship_move_b._assign_picking()
        ship_move_a._action_confirm()
        ship_move_b._action_confirm()
        pack_move_a = ship_move_a.move_orig_ids[0]
        pick_move_a = pack_move_a.move_orig_ids[0]

        pick_picking = pick_move_a.picking_id
        packing_picking = pack_move_a.picking_id
        shipping_picking = ship_move_a.picking_id

        pick_picking.picking_type_id.show_entire_packs = True
        packing_picking.picking_type_id.show_entire_packs = True
        shipping_picking.picking_type_id.show_entire_packs = True

        pick_picking.action_assign()
        self.assertEqual(len(pick_picking.move_ids_without_package), 2)
        pick_picking.move_line_ids.filtered(lambda ml: ml.product_id == self.productA).qty_done = 1.0
        pick_picking.move_line_ids.filtered(lambda ml: ml.product_id == self.productB).qty_done = 2.0

        first_pack = pick_picking.put_in_pack()
        self.assertEquals(len(pick_picking.package_level_ids), 1, 'Put some products in pack should create a package_level')
        self.assertEquals(pick_picking.package_level_ids[0].state, 'new', 'A new pack should be in state "new"')
        pick_picking.move_line_ids.filtered(lambda ml: ml.product_id == self.productA and ml.qty_done == 0.0).qty_done = 4.0
        pick_picking.move_line_ids.filtered(lambda ml: ml.product_id == self.productB and ml.qty_done == 0.0).qty_done = 3.0
        second_pack = pick_picking.put_in_pack()
        self.assertEqual(len(pick_picking.move_ids_without_package), 0)
        self.assertEqual(len(packing_picking.move_ids_without_package), 2)
        pick_picking.button_validate()
        self.assertEqual(len(packing_picking.move_ids_without_package), 0)
        self.assertEqual(len(first_pack.quant_ids), 2)
        self.assertEqual(len(second_pack.quant_ids), 2)
        packing_picking.action_assign()
        self.assertEqual(len(packing_picking.package_level_ids), 2, 'Two package levels must be created after assigning picking')
        packing_picking.package_level_ids.write({'is_done': True})
        packing_picking.action_done()

    def test_pick_a_pack_confirm(self):
        pack = self.env['stock.quant.package'].create({'name': 'The pack to pick'})
        self.env['stock.quant']._update_available_quantity(self.productA, self.stock_location, 20.0, package_id=pack)
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.int_type_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.stock_location.id,
            'state': 'draft',
        })
        picking.picking_type_id.show_entire_packs = True
        package_level = self.env['stock.package_level'].create({
            'package_id': pack.id,
            'picking_id': picking.id,
            'location_dest_id': self.stock_location.id,
            'company_id': picking.company_id.id,
        })
        self.assertEquals(package_level.state, 'draft',
                          'The package_level should be in draft as it has no moves, move lines and is not confirmed')
        picking.action_confirm()
        self.assertEqual(len(picking.move_ids_without_package), 0)
        self.assertEqual(len(picking.move_lines), 1,
                         'One move should be created when the package_level has been confirmed')
        self.assertEquals(len(package_level.move_ids), 1,
                          'The move should be in the package level')
        self.assertEquals(package_level.state, 'confirmed',
                          'The package level must be state confirmed when picking is confirmed')
        picking.action_assign()
        self.assertEqual(len(picking.move_lines), 1,
                         'You still have only one move when the picking is assigned')
        self.assertEqual(len(picking.move_lines.move_line_ids), 1,
                         'The move  should have one move line which is the reservation')
        self.assertEquals(picking.move_line_ids.package_level_id.id, package_level.id,
                          'The move line created should be linked to the package level')
        self.assertEquals(picking.move_line_ids.package_id.id, pack.id,
                          'The move line must have been reserved on the package of the package_level')
        self.assertEquals(picking.move_line_ids.result_package_id.id, pack.id,
                          'The move line must have the same package as result package')
        self.assertEquals(package_level.state, 'assigned', 'The package level must be in state assigned')
        package_level.write({'is_done': True})
        self.assertEquals(len(package_level.move_line_ids), 1,
                          'The package level should still keep one move line after have been set to "done"')
        self.assertEquals(package_level.move_line_ids[0].qty_done, 20.0,
                          'All quantity in package must be procesed in move line')
        picking.button_validate()
        self.assertEqual(len(picking.move_lines), 1,
                         'You still have only one move when the picking is assigned')
        self.assertEqual(len(picking.move_lines.move_line_ids), 1,
                         'The move  should have one move line which is the reservation')
        self.assertEquals(package_level.state, 'done', 'The package level must be in state done')
        self.assertEquals(pack.location_id.id, picking.location_dest_id.id,
                          'The quant package must be in the destination location')
        self.assertEquals(pack.quant_ids[0].location_id.id, picking.location_dest_id.id,
                          'The quant must be in the destination location')

    def test_multi_pack_reservation(self):
        """ When we move entire packages, it is possible to have a multiple times
            the same package in package level list, we make sure that only one is reserved,
            and that the location_id of the package is the one where the package is once it
            is reserved.
        """
        pack = self.env['stock.quant.package'].create({'name': 'The pack to pick'})
        shelf1_location = self.env['stock.location'].create({
            'name': 'shelf1',
            'usage': 'internal',
            'location_id': self.stock_location.id,
        })
        self.env['stock.quant']._update_available_quantity(self.productA, shelf1_location, 20.0, package_id=pack)
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.int_type_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.stock_location.id,
            'state': 'draft',
        })
        package_level = self.env['stock.package_level'].create({
            'package_id': pack.id,
            'picking_id': picking.id,
            'location_dest_id': self.stock_location.id,
            'company_id': picking.company_id.id,
        })
        package_level = self.env['stock.package_level'].create({
            'package_id': pack.id,
            'picking_id': picking.id,
            'location_dest_id': self.stock_location.id,
            'company_id': picking.company_id.id,
        })
        picking.action_confirm()
        self.assertEqual(picking.package_level_ids.mapped('location_id.id'), [self.stock_location.id],
                         'The package levels should still in the same location after confirmation.')
        picking.action_assign()
        package_level_reserved = picking.package_level_ids.filtered(lambda pl: pl.state == 'assigned')
        package_level_confirmed = picking.package_level_ids.filtered(lambda pl: pl.state == 'confirmed')
        self.assertEqual(package_level_reserved.location_id.id, shelf1_location.id, 'The reserved package level must be reserved in shelf1')
        self.assertEqual(package_level_confirmed.location_id.id, self.stock_location.id, 'The not reserved package should keep its location')
        picking.do_unreserve()
        self.assertEqual(picking.package_level_ids.mapped('location_id.id'), [self.stock_location.id],
                         'The package levels should have back the original location.')
        picking.package_level_ids.write({'is_done': True})
        picking.action_assign()
        package_level_reserved = picking.package_level_ids.filtered(lambda pl: pl.state == 'assigned')
        package_level_confirmed = picking.package_level_ids.filtered(lambda pl: pl.state == 'confirmed')
        self.assertEqual(package_level_reserved.location_id.id, shelf1_location.id, 'The reserved package level must be reserved in shelf1')
        self.assertEqual(package_level_confirmed.location_id.id, self.stock_location.id, 'The not reserved package should keep its location')
        self.assertEqual(picking.package_level_ids.mapped('is_done'), [True, True], 'Both package should still done')

    def test_put_in_pack_to_different_location(self):
        """ Hitting 'Put in pack' button while some move lines go to different
            location should trigger a wizard. This wizard applies the same destination
            location to all the move lines
        """
        self.warehouse.in_type_id.show_reserved = True
        shelf1_location = self.env['stock.location'].create({
            'name': 'shelf1',
            'usage': 'internal',
            'location_id': self.stock_location.id,
        })
        shelf2_location = self.env['stock.location'].create({
            'name': 'shelf2',
            'usage': 'internal',
            'location_id': self.stock_location.id,
        })
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.stock_location.id,
            'state': 'draft',
        })
        ship_move_a = self.env['stock.move'].create({
            'name': 'move 1',
            'product_id': self.productA.id,
            'product_uom_qty': 5.0,
            'product_uom': self.productA.uom_id.id,
            'location_id': self.customer_location.id,
            'location_dest_id': shelf1_location.id,
            'picking_id': picking.id,
            'state': 'draft',
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_line_ids.filtered(lambda ml: ml.product_id == self.productA).qty_done = 5.0
        picking.put_in_pack()
        pack1 = self.env['stock.quant.package'].search([])[-1]
        picking.write({
            'move_line_ids': [(0, 0, {
                'product_id': self.productB.id,
                'product_uom_qty': 7.0,
                'qty_done': 7.0,
                'product_uom_id': self.productB.uom_id.id,
                'location_id': self.customer_location.id,
                'location_dest_id': shelf2_location.id,
                'picking_id': picking.id,
                'state': 'confirmed',
            })]
        })
        picking.write({
            'move_line_ids': [(0, 0, {
                'product_id': self.productA.id,
                'product_uom_qty': 5.0,
                'qty_done': 5.0,
                'product_uom_id': self.productA.uom_id.id,
                'location_id': self.customer_location.id,
                'location_dest_id': shelf1_location.id,
                'picking_id': picking.id,
                'state': 'confirmed',
            })]
        })
        wizard_values = picking.put_in_pack()
        wizard = self.env[(wizard_values.get('res_model'))].browse(wizard_values.get('res_id'))
        wizard.location_dest_id = shelf2_location.id
        wizard.action_done()
        picking.action_done()
        pack2 = self.env['stock.quant.package'].search([])[-1]
        self.assertEqual(pack2.location_id.id, shelf2_location.id, 'The package must be stored  in shelf2')
        self.assertEqual(pack1.location_id.id, shelf1_location.id, 'The package must be stored  in shelf1')
        qp1 = pack2.quant_ids[0]
        qp2 = pack2.quant_ids[1]
        self.assertEqual(qp1.quantity + qp2.quantity, 12, 'The quant has not the good quantity')

    def test_move_picking_with_package(self):
        """
        355.4 rounded with 0.001 precision is 355.40000000000003.
        check that nonetheless, moving a picking is accepted
        """
        self.assertEqual(self.productA.uom_id.rounding, 0.001)
        self.assertEqual(
            float_round(355.4, precision_rounding=self.productA.uom_id.rounding),
            355.40000000000003,
        )
        location_dict = {
            'location_id': self.stock_location.id,
        }
        quant = self.env['stock.quant'].create({
            **location_dict,
            **{'product_id': self.productA.id, 'quantity': 355.4},  # important number
        })
        package = self.env['stock.quant.package'].create({
            **location_dict, **{'quant_ids': [(6, 0, [quant.id])]},
        })
        location_dict.update({
            'state': 'draft',
            'location_dest_id': self.ship_location.id,
        })
        move = self.env['stock.move'].create({
            **location_dict,
            **{
                'name': "XXX",
                'product_id': self.productA.id,
                'product_uom': self.productA.uom_id.id,
                'product_uom_qty': 355.40000000000003,  # other number
            }})
        picking = self.env['stock.picking'].create({
            **location_dict,
            **{
                'picking_type_id': self.warehouse.in_type_id.id,
                'move_lines': [(6, 0, [move.id])],
        }})

        picking.action_confirm()
        picking.action_assign()
        move.quantity_done = move.reserved_availability
        picking.action_done()
        # if we managed to get there, there was not any exception
        # complaining that 355.4 is not 355.40000000000003. Good job!

    def test_move_picking_with_package_2(self):
        """ Generate two move lines going to different location in the same
        package.
        """
        shelf1 = self.env['stock.location'].create({
            'location_id': self.stock_location.id,
            'name': 'Shelf 1',
        })
        shelf2 = self.env['stock.location'].create({
            'location_id': self.stock_location.id,
            'name': 'Shelf 2',
        })
        package = self.env['stock.quant.package'].create({})

        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.stock_location.id,
            'state': 'draft',
        })
        self.env['stock.move.line'].create({
            'location_id': self.stock_location.id,
            'location_dest_id': shelf1.id,
            'product_id': self.productA.id,
            'product_uom_id': self.productA.uom_id.id,
            'qty_done': 5.0,
            'picking_id': picking.id,
            'result_package_id': package.id,
        })
        self.env['stock.move.line'].create({
            'location_id': self.stock_location.id,
            'location_dest_id': shelf2.id,
            'product_id': self.productA.id,
            'product_uom_id': self.productA.uom_id.id,
            'qty_done': 5.0,
            'picking_id': picking.id,
            'result_package_id': package.id,
        })
        picking.action_confirm()
        with self.assertRaises(UserError):
            picking.action_done()

    def test_pack_in_receipt_two_step_single_putway(self):
        """ Checks all works right in the following specific corner case:

          * For a two-step receipt, receives two products using the same putaway
          * Puts these products in a package then valid the receipt.
          * Cancels the automatically generated internal transfer then create a new one.
          * In this internal transfer, adds the package then valid it.
        """
        grp_multi_loc = self.env.ref('stock.group_stock_multi_locations')
        grp_multi_step_rule = self.env.ref('stock.group_adv_location')
        grp_pack = self.env.ref('stock.group_tracking_lot')
        self.env.user.write({'groups_id': [(3, grp_multi_loc.id)]})
        self.env.user.write({'groups_id': [(3, grp_multi_step_rule.id)]})
        self.env.user.write({'groups_id': [(3, grp_pack.id)]})
        self.warehouse.reception_steps = 'two_steps'
        # Settings of receipt.
        self.warehouse.in_type_id.show_operations = True
        self.warehouse.in_type_id.show_entire_packs = True
        self.warehouse.in_type_id.show_reserved = True
        # Settings of internal transfer.
        self.warehouse.int_type_id.show_operations = True
        self.warehouse.int_type_id.show_entire_packs = True
        self.warehouse.int_type_id.show_reserved = True

        # Creates two new locations for putaway.
        location_form = Form(self.env['stock.location'])
        location_form.name = 'Shelf A'
        location_form.location_id = self.stock_location
        loc_shelf_A = location_form.save()

        # Creates a new putaway rule for productA and productB.
        putaway_A = self.env['stock.putaway.rule'].create({
            'product_id': self.productA.id,
            'location_in_id': self.stock_location.id,
            'location_out_id': loc_shelf_A.id,
        })
        putaway_B = self.env['stock.putaway.rule'].create({
            'product_id': self.productB.id,
            'location_in_id': self.stock_location.id,
            'location_out_id': loc_shelf_A.id,
        })
        self.stock_location.putaway_rule_ids = [(4, putaway_A.id, 0), (4, putaway_B.id, 0)]

        # Create a new receipt with the two products.
        receipt_form = Form(self.env['stock.picking'])
        receipt_form.picking_type_id = self.warehouse.in_type_id
        # Add 2 lines
        with receipt_form.move_ids_without_package.new() as move_line:
            move_line.product_id = self.productA
            move_line.product_uom_qty = 1
        with receipt_form.move_ids_without_package.new() as move_line:
            move_line.product_id = self.productB
            move_line.product_uom_qty = 1
        receipt = receipt_form.save()
        receipt.action_confirm()

        # Adds quantities then packs them and valids the receipt.
        receipt_form = Form(receipt)
        with receipt_form.move_line_ids_without_package.edit(0) as move_line:
            move_line.qty_done = 1
        with receipt_form.move_line_ids_without_package.edit(1) as move_line:
            move_line.qty_done = 1
        receipt = receipt_form.save()
        receipt.put_in_pack()
        receipt.button_validate()

        receipt_package = receipt.package_level_ids_details[0]
        self.assertEqual(receipt_package.location_dest_id.id, receipt.location_dest_id.id)
        self.assertEqual(
            receipt_package.move_line_ids[0].location_dest_id.id,
            receipt.location_dest_id.id)
        self.assertEqual(
            receipt_package.move_line_ids[1].location_dest_id.id,
            receipt.location_dest_id.id)

        # Checks an internal transfer was created following the validation of the receipt.
        internal_transfer = self.env['stock.picking'].search([
            ('picking_type_id', '=', self.warehouse.int_type_id.id)
        ], order='id desc', limit=1)
        self.assertEqual(internal_transfer.origin, receipt.name)
        self.assertEqual(
            len(internal_transfer.package_level_ids_details), 1)
        internal_package = internal_transfer.package_level_ids_details[0]
        self.assertNotEqual(
            internal_package.location_dest_id.id,
            internal_transfer.location_dest_id.id)
        self.assertEqual(
            internal_package.location_dest_id.id,
            putaway_A.location_out_id.id,
            "The package destination location must be the one from the putaway.")
        self.assertEqual(
            internal_package.move_line_ids[0].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the putaway.")
        self.assertEqual(
            internal_package.move_line_ids[1].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the putaway.")

        # Cancels the internal transfer and creates a new one.
        internal_transfer.action_cancel()
        internal_form = Form(self.env['stock.picking'])
        internal_form.picking_type_id = self.warehouse.int_type_id
        internal_form.location_id = self.warehouse.wh_input_stock_loc_id
        with internal_form.package_level_ids_details.new() as pack_line:
            pack_line.package_id = receipt_package.package_id
        internal_transfer = internal_form.save()

        # Checks the package fields have been correctly set.
        internal_package = internal_transfer.package_level_ids_details[0]
        self.assertEqual(
            internal_package.location_dest_id.id,
            internal_transfer.location_dest_id.id)
        internal_transfer.action_assign()
        self.assertNotEqual(
            internal_package.location_dest_id.id,
            internal_transfer.location_dest_id.id)
        self.assertEqual(
            internal_package.location_dest_id.id,
            putaway_A.location_out_id.id,
            "The package destination location must be the one from the putaway.")
        self.assertEqual(
            internal_package.move_line_ids[0].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the putaway.")
        self.assertEqual(
            internal_package.move_line_ids[1].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the putaway.")
        internal_transfer.button_validate()

    def test_pack_in_receipt_two_step_multi_putaway(self):
        """ Checks all works right in the following specific corner case:

          * For a two-step receipt, receives two products using two putaways
          targeting different locations.
          * Puts these products in a package then valid the receipt.
          * Cancels the automatically generated internal transfer then create a new one.
          * In this internal transfer, adds the package then valid it.
        """
        grp_multi_loc = self.env.ref('stock.group_stock_multi_locations')
        grp_multi_step_rule = self.env.ref('stock.group_adv_location')
        grp_pack = self.env.ref('stock.group_tracking_lot')
        self.env.user.write({'groups_id': [(3, grp_multi_loc.id)]})
        self.env.user.write({'groups_id': [(3, grp_multi_step_rule.id)]})
        self.env.user.write({'groups_id': [(3, grp_pack.id)]})
        self.warehouse.reception_steps = 'two_steps'
        # Settings of receipt.
        self.warehouse.in_type_id.show_operations = True
        self.warehouse.in_type_id.show_entire_packs = True
        self.warehouse.in_type_id.show_reserved = True
        # Settings of internal transfer.
        self.warehouse.int_type_id.show_operations = True
        self.warehouse.int_type_id.show_entire_packs = True
        self.warehouse.int_type_id.show_reserved = True

        # Creates two new locations for putaway.
        location_form = Form(self.env['stock.location'])
        location_form.name = 'Shelf A'
        location_form.location_id = self.stock_location
        loc_shelf_A = location_form.save()
        location_form = Form(self.env['stock.location'])
        location_form.name = 'Shelf B'
        location_form.location_id = self.stock_location
        loc_shelf_B = location_form.save()

        # Creates a new putaway rule for productA and productB.
        putaway_A = self.env['stock.putaway.rule'].create({
            'product_id': self.productA.id,
            'location_in_id': self.stock_location.id,
            'location_out_id': loc_shelf_A.id,
        })
        putaway_B = self.env['stock.putaway.rule'].create({
            'product_id': self.productB.id,
            'location_in_id': self.stock_location.id,
            'location_out_id': loc_shelf_B.id,
        })
        self.stock_location.putaway_rule_ids = [(4, putaway_A.id, 0), (4, putaway_B.id, 0)]
        # location_form = Form(self.stock_location)
        # location_form.putaway_rule_ids = [(4, putaway_A.id, 0), (4, putaway_B.id, 0), ],
        # self.stock_location = location_form.save()

        # Create a new receipt with the two products.
        receipt_form = Form(self.env['stock.picking'])
        receipt_form.picking_type_id = self.warehouse.in_type_id
        # Add 2 lines
        with receipt_form.move_ids_without_package.new() as move_line:
            move_line.product_id = self.productA
            move_line.product_uom_qty = 1
        with receipt_form.move_ids_without_package.new() as move_line:
            move_line.product_id = self.productB
            move_line.product_uom_qty = 1
        receipt = receipt_form.save()
        receipt.action_confirm()

        # Adds quantities then packs them and valids the receipt.
        receipt_form = Form(receipt)
        with receipt_form.move_line_ids_without_package.edit(0) as move_line:
            move_line.qty_done = 1
        with receipt_form.move_line_ids_without_package.edit(1) as move_line:
            move_line.qty_done = 1
        receipt = receipt_form.save()
        receipt.put_in_pack()
        receipt.button_validate()

        receipt_package = receipt.package_level_ids_details[0]
        self.assertEqual(receipt_package.location_dest_id.id, receipt.location_dest_id.id)
        self.assertEqual(
            receipt_package.move_line_ids[0].location_dest_id.id,
            receipt.location_dest_id.id)
        self.assertEqual(
            receipt_package.move_line_ids[1].location_dest_id.id,
            receipt.location_dest_id.id)

        # Checks an internal transfer was created following the validation of the receipt.
        internal_transfer = self.env['stock.picking'].search([
            ('picking_type_id', '=', self.warehouse.int_type_id.id)
        ], order='id desc', limit=1)
        self.assertEqual(internal_transfer.origin, receipt.name)
        self.assertEqual(
            len(internal_transfer.package_level_ids_details), 1)
        internal_package = internal_transfer.package_level_ids_details[0]
        self.assertEqual(
            internal_package.location_dest_id.id,
            internal_transfer.location_dest_id.id)
        self.assertNotEqual(
            internal_package.location_dest_id.id,
            putaway_A.location_out_id.id,
            "The package destination location must be the one from the picking.")
        self.assertNotEqual(
            internal_package.move_line_ids[0].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the picking.")
        self.assertNotEqual(
            internal_package.move_line_ids[1].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the picking.")

        # Cancels the internal transfer and creates a new one.
        internal_transfer.action_cancel()
        internal_form = Form(self.env['stock.picking'])
        internal_form.picking_type_id = self.warehouse.int_type_id
        internal_form.location_id = self.warehouse.wh_input_stock_loc_id
        with internal_form.package_level_ids_details.new() as pack_line:
            pack_line.package_id = receipt_package.package_id
        internal_transfer = internal_form.save()

        # Checks the package fields have been correctly set.
        internal_package = internal_transfer.package_level_ids_details[0]
        self.assertEqual(
            internal_package.location_dest_id.id,
            internal_transfer.location_dest_id.id)
        internal_transfer.action_assign()
        self.assertEqual(
            internal_package.location_dest_id.id,
            internal_transfer.location_dest_id.id)
        self.assertNotEqual(
            internal_package.location_dest_id.id,
            putaway_A.location_out_id.id,
            "The package destination location must be the one from the picking.")
        self.assertNotEqual(
            internal_package.move_line_ids[0].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the picking.")
        self.assertNotEqual(
            internal_package.move_line_ids[1].location_dest_id.id,
            putaway_A.location_out_id.id,
            "The move line destination location must be the one from the picking.")
        internal_transfer.button_validate()
