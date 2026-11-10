import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";

// On the static items of the Actions menu, as a bound server action would show without an icon.
patch(ListController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);
        if (this.props.resModel === "fleet.vehicle.log.contract") {
            items.fillDefaultProducts = {
                sequence: 47,
                icon: "fa fa-cubes",
                description: _t("Fill Default Products"),
                callback: () => this.onFillDefaultProducts(),
            };
        }
        return items;
    },

    async onFillDefaultProducts() {
        const resIds = await this.model.root.getResIds(true);
        const action = await this.orm.call(this.props.resModel, "action_fill_default_products", [resIds]);
        await this.actionService.doAction(action);
    },
});
