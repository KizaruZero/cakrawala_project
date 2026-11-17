import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/** Helpdesk Overview: one counter per stage of the team, opening its tickets in that stage. */
export class HelpdeskStageCounters extends Component {
    static template = "x_helpdesk_enhance.HelpdeskStageCounters";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    get stages() {
        return this.props.record.data[this.props.name] || [];
    }

    async openStage(stage) {
        const action = await this.orm.call("helpdesk.team", "action_view_stage_tickets", [
            [this.props.record.resId],
            stage.id,
        ]);
        await this.action.doAction(action);
    }
}

registry.category("fields").add("helpdesk_stage_counters", {
    component: HelpdeskStageCounters,
    supportedTypes: ["json"],
});
