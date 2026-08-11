# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Generate normalized incentive multiplier defaults on a fresh install."""
    env['rpc.incentive.factor']._ensure_default_rules()
