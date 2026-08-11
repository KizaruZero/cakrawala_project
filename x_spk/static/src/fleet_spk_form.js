import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { ListController } from "@web/views/list/list_controller";

const POLICY = {
    "fleet.spk": {
        fields: ["state"],
        canDelete: (data) => data.state === "new",
        canArchive: (data) => data.state !== "new",
    },
};

function restrict(items, key, allowed) {
    const item = items[key];
    if (!item) {
        return;
    }
    const base = item.isAvailable;
    item.isAvailable = () => (base === undefined || base()) && allowed();
}

function readable(policy, data) {
    return !!data && policy.fields.every((field) => data[field] !== undefined);
}

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);
        const policy = POLICY[this.model?.root?.resModel];
        const data = this.model?.root?.data;
        if (!policy || !readable(policy, data)) {
            return items;
        }
        restrict(items, "delete", () => policy.canDelete(data));
        restrict(items, "archive", () => policy.canArchive(data));
        return items;
    },
});

patch(ListController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);
        const policy = POLICY[this.props.resModel];
        const records = this.model?.root?.selection || [];
        if (!policy || !records.length || this.model.root.isDomainSelected) {
            return items;
        }
        if (!records.every((record) => readable(policy, record.data))) {
            return items;
        }
        restrict(items, "delete", () => records.every((r) => policy.canDelete(r.data)));
        restrict(items, "archive", () => records.every((r) => policy.canArchive(r.data)));
        return items;
    },
});
