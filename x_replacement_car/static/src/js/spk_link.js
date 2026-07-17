document.addEventListener('click', function(ev) {
    const link = ev.target.closest('.o_spk_link');
    if (link) {
        ev.preventDefault();
        ev.stopPropagation();
        const spkId = parseInt(link.getAttribute('data-spk-id'));
        if (spkId) {
            const wowl = window.odoo && window.odoo.__WOWL__;
            const actionService = wowl && wowl.env && wowl.env.services && wowl.env.services.action;
            if (actionService) {
                actionService.doAction("x_spk.fleet_spk_action", {
                    resId: spkId,
                });
            } else {
                window.location.href = '/odoo/action-591/' + spkId;
            }
        }
    }
}, true); 
