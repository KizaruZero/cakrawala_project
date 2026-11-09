import { expect, mockTimeZone, test } from "@odoo/hoot";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { getPickerCell } from "@web/../tests/core/datetime/datetime_test_helpers";
import {
    clickSave, contains, defineModels, defineParams, fields, models, mountView, onRpc,
} from "@web/../tests/web_test_helpers";
import { formatEstimatedDeliveryDate } from "@x_crm_custom/js/estimated_delivery_date_field";

class Lead extends models.Model {
    _name = "crm.lead";
    name = fields.Char();
    estimated_delivery = fields.Date();
    other_date = fields.Date();
    _records = [{
        id: 1, name: "Delivery date test", estimated_delivery: "2026-02-01",
        other_date: "2026-02-01",
    }];
}
defineModels([Lead]);
defineMailModels();

const selector = '.o_field_widget[name="estimated_delivery"]';
const arch = `<form>
    <field name="name"/>
    <field name="estimated_delivery" widget="crm_estimated_delivery_date"/>
</form>`;

test("readonly date has the requested format and other date fields keep their format", async () => {
    defineParams({ lang_parameters: { date_format: "%m/%d/%Y" } });
    await mountView({
        resModel: "crm.lead", resId: 1, type: "form",
        arch: `<form>
            <field name="estimated_delivery" widget="crm_estimated_delivery_date" readonly="1"/>
            <field name="other_date" readonly="1" options="{'numeric': True}"/>
        </form>`,
    });
    expect(selector).toHaveText("01, Feb 2026");
    expect('.o_field_widget[name="other_date"]').toHaveText("02/01/2026");
});

test("editable date retains the native picker and saves an ISO date", async () => {
    await mountView({ resModel: "crm.lead", resId: 1, type: "form", arch });
    expect(selector).toHaveText("01, Feb 2026");
    onRpc("web_save", ({ args }) => expect.step(args[1].estimated_delivery));
    await contains(`${selector} button`).click();
    expect(".o_datetime_picker").toHaveCount(1);
    await contains(getPickerCell(22)).click();
    expect(selector).toHaveText("22, Feb 2026");
    await clickSave();
    expect.verifySteps(["2026-02-22"]);
});

test("an empty estimated date remains empty and editable", async () => {
    Lead._records[0].estimated_delivery = false;
    await mountView({ resModel: "crm.lead", resId: 1, type: "form", arch });
    expect(selector).toHaveText("");
    expect(`${selector} input`).toHaveValue("");
});

test("format uses English short months, padded days and full years without mutating dates", () => {
    mockTimeZone(-11);
    const date = luxon.DateTime.fromISO("2024-02-29", { locale: "fr" });
    expect(formatEstimatedDeliveryDate(date)).toBe("29, Feb 2024");
    expect(date.locale).toBe("fr");
    expect(date.toISODate()).toBe("2024-02-29");
    expect(formatEstimatedDeliveryDate(luxon.DateTime.fromISO("2026-09-01"))).toBe("01, Sep 2026");
    expect(formatEstimatedDeliveryDate(false)).toBe("");
});
