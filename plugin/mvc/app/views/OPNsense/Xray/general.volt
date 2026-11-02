{# Only the instance selectors on this page; leave OPNsense theme controls unchanged. #}
<style>
    #xray-instance-tabs .xray-instance-selector {
        flex: 0 1 260px;
        width: 260px;
        max-width: 100%;
        min-width: 0;
        table-layout: fixed;
    }
    #xray-instance-tabs .xray-instance-selector > .input-group-addon {
        width: 34px;
    }
    #xray-instance-tabs .xray-instance-selector > select.form-control {
        /* The theme's small select line-height includes the padded field height. */
        line-height: normal;
        min-width: 0;
        padding-right: 24px;
        white-space: nowrap;
        text-overflow: ellipsis;
    }
</style>

{{ partial('OPNsense/Xray/partials/scripts') }}

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#instances">{{ lang._('Instances') }}</a></li>
    <li><a data-toggle="tab" href="#general">{{ lang._('General') }}</a></li>
    <li><a data-toggle="tab" href="#diagnostics">{{ lang._('Diagnostics') }}</a></li>
    <li><a data-toggle="tab" href="#logs">{{ lang._('Log') }}</a></li>
</ul>

<div id="xray-instance-tabs" class="tab-content content-box">
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
