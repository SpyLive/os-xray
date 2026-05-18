{{ partial('OPNsense/Xray/partials/scripts') }}

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#instances">{{ lang._('Instances') }}</a></li>
    <li><a data-toggle="tab" href="#general">{{ lang._('General') }}</a></li>
    <li><a data-toggle="tab" href="#diagnostics">{{ lang._('Diagnostics') }}</a></li>
    <li><a data-toggle="tab" href="#logs">{{ lang._('Log') }}</a></li>
</ul>

<div class="tab-content content-box">
    {{ partial('OPNsense/Xray/partials/tab_instances') }}

    <div id="general" class="tab-pane fade in">
        {{ partial("layout_partials/base_form", {'fields': generalForm, 'id': 'frm_general_settings'}) }}
    </div>

    {{ partial('OPNsense/Xray/partials/tab_diagnostics') }}
    {{ partial('OPNsense/Xray/partials/tab_logs') }}
</div>

{{ partial('layout_partials/base_apply_button', {'data_endpoint': '/api/xray/service/reconfigure'}) }}

{{ partial("layout_partials/base_dialog", ['fields': instanceForm, 'id': 'DialogInstance', 'label': lang._('Edit Instance')]) }}

{{ partial('OPNsense/Xray/partials/modal_debug') }}
