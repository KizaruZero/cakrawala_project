def post_init_hook(env):
    env['x.cleanup.target'].action_load_preset()


def uninstall_hook(env):
    # the server actions bound to the cleaned models are created at runtime, without an XML id:
    # remove them so that no "Data Cleanup" entry is left in the Action menus
    targets = env['x.cleanup.target'].with_context(active_test=False).search([])
    (targets.action_delete_id | targets.action_archive_id).sudo().unlink()
