import { ListRenderer } from "@web/views/list/list_renderer";
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

export class BastkSectionListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.displayType = "line_section";
        this.titleField = "name";
    }

    isSection(record) {
        return record.data.display_type === this.displayType;
    }

    getSectionColspan(record) {
        let cols = this.getColumns(record);
        let colspan = cols ? cols.length : this.columns.length;
        if (this.hasSelectors) {
            colspan++;
        }
        if (this.displayOptionalFields || (this.activeActions && this.activeActions.onDelete) || this.hasX2ManyAction) {
            colspan++;
        }
        return colspan || 3;
    }
}
BastkSectionListRenderer.template = "x_bastk_management.BastkSectionListRenderer";
BastkSectionListRenderer.recordRowTemplate = "x_bastk_management.BastkSectionListRenderer.RecordRow";

export class BastkSectionOneToManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: BastkSectionListRenderer,
    };
    static defaultProps = {
        ...X2ManyField.defaultProps,
        editable: "bottom",
    };
}

registry.category("fields").add("bastk_section_one2many", {
    ...x2ManyField,
    component: BastkSectionOneToManyField,
    additionalClasses: [...(x2ManyField.additionalClasses || []), "o_field_one2many", "o_bastk_section_one2many"],
});
