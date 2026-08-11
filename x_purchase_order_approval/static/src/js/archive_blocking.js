import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { ListController } from "@web/views/list/list_controller";

const POLICY = {
    "purchase.order": {
        fields: ["state"],
        canDelete: (data) => ["draft", "sent", "cancel"].includes(data.state),
        canArchive: (data) => !["draft", "sent"].includes(data.state),
    },
    "purchase.requisition": {
        fields: ["state"],
        canDelete: (data) => ["draft", "cancel"].includes(data.state),
        canArchive: (data) => data.state !== "draft",
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

    async deleteRecord() {
        if (!POLICY[this.model?.root?.resModel]) {
            return super.deleteRecord(...arguments);
        }
        this.deleteRecordsWithConfirmation(
            {
                confirm: async () => {
                    await this.model.root.delete();
                    this.env.config.historyBack();
                },
            },
            [this.model.root]
        );
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
