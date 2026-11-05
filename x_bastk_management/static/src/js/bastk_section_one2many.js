import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ListRenderer } from "@web/views/list/list_renderer";
import { registry } from "@web/core/registry";
import { getFieldDomain } from "@web/model/relational_model/utils";
import { useSpecialData } from "@web/views/fields/relational_utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

const selectionItemsCache = new Map();

export class BastkSelectionChecklistField extends Component {
    static template = "x_bastk_management.BastkSelectionChecklistField";
    static props = {
        ...standardFieldProps,
        domain: { type: [Array, Function], optional: true },
    };

    setup() {
        this.type = this.props.record.fields[this.props.name]?.type;
        if (this.type === "many2one") {
            this.specialData = useSpecialData(async (orm, props) => {
                const { relation } = props.record.fields[props.name];
                const domain = getFieldDomain(props.record, props.name, props.domain);
                const cacheKey = `${relation}:${JSON.stringify(domain || [])}`;
                const kwargs = {
                    specification: { display_name: 1 },
                    domain,
                };
                const { records } = await orm.call(relation, "web_search_read", [], kwargs);
                const mapped = records.map((record) => [record.id, record.display_name]);
                selectionItemsCache.set(cacheKey, mapped);
                return mapped;
            });
        }
    }

    get items() {
        if (this.type === "many2one") {
            if (this.specialData?.data?.length) {
                return this.specialData.data;
            }
            const { relation } = this.props.record.fields[this.props.name];
            const domain = getFieldDomain(this.props.record, this.props.name, this.props.domain);
            const cacheKey = `${relation}:${JSON.stringify(domain || [])}`;
            return selectionItemsCache.get(cacheKey) || this.specialData?.data || [];
        }
        if (this.type === "selection") {
            return this.props.record.fields[this.props.name].selection || [];
        }
        return [];
    }

    get value() {
        const val = this.props.record.data[this.props.name];
        if (!val) {
            return null;
        }
        if (this.type === "many2one") {
            return Array.isArray(val) ? val[0] : val.id;
        }
        return val;
    }

    async onToggleItem(item, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        if (this.props.readonly) {
            return;
        }
        const isSelected = this.value === item[0];
        if (this.type === "many2one") {
            await this.props.record.update({
                [this.props.name]: isSelected ? false : { id: item[0], display_name: item[1] },
            });
        } else if (this.type === "selection") {
            await this.props.record.update({
                [this.props.name]: isSelected ? false : item[0],
            });
        }
    }
}

export const bastkSelectionChecklistField = {
    component: BastkSelectionChecklistField,
    displayName: _t("BASTK Selection Checklist"),
    supportedTypes: ["many2one", "selection"],
    isEmpty: (record, fieldName) => !record.data[fieldName],
    extractProps: (_fieldInfo, dynamicInfo) => ({
        domain: dynamicInfo.domain,
        readonly: dynamicInfo.readonly,
    }),
};

registry.category("fields").add("bastk_selection_checklist", bastkSelectionChecklistField);

export class BastkSectionListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.displayType = "line_section";
        this.titleField = "name";
    }

    isSection(record) {
        return record.data.display_type === this.displayType;
    }

    async onCellClicked(record, column, ev, newWindow) {
        if (
            (column && column.name === "selection_id") ||
            ev?.target?.closest?.(".o_bastk_selection_checklist")
        ) {
            return;
        }
        return super.onCellClicked(record, column, ev, newWindow);
    }

    getSectionColspan(record) {
        let cols = typeof this.getColumns === "function" ? this.getColumns(record) : this.columns;
        let visibleCols = (cols || []).filter((c) => !c.column_invisible);
        let colspan = visibleCols.length || (this.columns ? this.columns.length : 3);
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
    additionalClasses: [...(x2ManyField.additionalClasses || []), "o_field_one2many", "o_bastk_section_one2many", "w-100"],
});
