"""Small deterministic policy functions; no dependency on the Odoo runtime."""
def required_layers(layers, amount):
    return sorted((layer for layer in layers if amount >= layer.min_amount),
                  key=lambda layer: (layer.sequence, layer.id))

def may_approve(user_id, approver_id, delegate_id, valid_from, valid_until, today):
    return user_id == approver_id or bool(
        delegate_id and user_id == delegate_id and valid_from and valid_until
        and valid_from <= today <= valid_until)
