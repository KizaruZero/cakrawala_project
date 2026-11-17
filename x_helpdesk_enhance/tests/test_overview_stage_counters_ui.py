from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOverviewStageCountersUi(HttpCase):

    def test_overview_counter_opens_the_tickets_of_its_stage(self):
        new_test_user(self.env, 'overview_ui', groups='base.group_user,helpdesk.group_helpdesk_manager')
        stage = self.env['helpdesk.stage'].create({'name': 'UI Overview Stage', 'sequence': 950})
        team = self.env['helpdesk.team'].create({'name': 'UI Overview Team', 'stage_ids': [(6, 0, stage.ids)]})
        category = self.env['helpdesk.ticket.category'].create({'name': 'UI Overview Category'})
        self.env['helpdesk.ticket'].create([
            {'team_id': team.id, 'stage_id': stage.id, 'ticket_category_id': category.id} for _ in range(2)
        ])
        code = """
            (async () => {
                const wait = async (selector, check = () => true) => {
                    for (let i = 0; i < 150; i++) {
                        const el = [...document.querySelectorAll(selector)].find(check);
                        if (el) return el;
                        await new Promise((resolve) => setTimeout(resolve, 100));
                    }
                    throw new Error("Not found: " + selector);
                };
                const counter = await wait("a[title='UI Overview Stage']");
                // The native banner loads its figures asynchronously: give it time to show up.
                await new Promise((resolve) => setTimeout(resolve, 1000));
                if (document.querySelector(".o_helpdesk_banner")) {
                    throw new Error("The My Tickets / My Performance banner is still shown");
                }
                if (counter.querySelector(".fw-bold").textContent.trim() !== "2") {
                    throw new Error("Wrong count: " + counter.textContent);
                }
                counter.click();
                await wait(".o_breadcrumb", (el) => el.textContent.includes("UI Overview Team - UI Overview Stage"));
                await wait(".o_data_row", () => document.querySelectorAll(".o_data_row").length === 2);
                console.log("test successful");
            })().catch((error) => console.error(error.message));
        """
        self.browser_js('/odoo/action-helpdesk.helpdesk_team_dashboard_action_main', code, login='overview_ui')
