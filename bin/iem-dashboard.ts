#!/usr/bin/env node
import 'source-map-support/register';
import {App} from 'aws-cdk-lib';
import { IemDashboardStack } from '../src/stacks/metric-dashboard-stack';
import {AlarmDashboardStack} from "../src/stacks/alarm-dashboard-stack";
import { AwsSolutionsChecks } from 'cdk-nag'
import { Aspects } from 'aws-cdk-lib';
import {loadConfig} from "../config/config.schema";

const config = loadConfig();

if ( config.AlarmDashboard?.enabled && (!config.AlarmDashboard.organizationId || !config.AlarmDashboard.organizationId.startsWith("o-") ) ){
    throw new Error('Please edit `config/config.json` and add `organizationId` before continuing');
}


const app = new App();

Aspects.of(app).add(new AwsSolutionsChecks({verbose: true}));

if ( config.MetricDashboards && ! config.MetricDashboards.enabled ){
    console.log('Not deploying metric dashboards');
} else {
    new IemDashboardStack(app, `${config.BaseName}-Stack`, { config });
}

if ( config.AlarmDashboard && config.AlarmDashboard.enabled ){
    new AlarmDashboardStack(app,`${config.BaseName}-Alarm-Stack`, { config });
} else {
    console.log('Not deploying AlarmDashboard');
}
