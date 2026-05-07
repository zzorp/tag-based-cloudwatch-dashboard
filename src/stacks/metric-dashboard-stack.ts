import {Stack,StackProps} from 'aws-cdk-lib';
import {Construct} from 'constructs'
import {GraphFactory} from "../constructs/graph-factory";
import {Dashboard} from "aws-cdk-lib/aws-cloudwatch";
import {loadConfig} from "../../config/config.schema";
import {AppConfig} from "../types/config";

export interface IemDashboardStackProps extends StackProps {
  config?: AppConfig;
}

export class IemDashboardStack extends Stack {
  constructor(scope: Construct, id: string, props?: IemDashboardStackProps) {
    super(scope, id, props);

    const config = props?.config ?? loadConfig();

    const dashboard = new Dashboard(this,config.BaseName,{
      dashboardName: config.BaseName + '-Dashboard'
    });

    let resources:any = [];
    try {
      resources = require(config.ResourceFile);
      console.log(`LOADED RESOURCE FILE ${config.ResourceFile}`);
    } catch {
      console.log(`ERROR: ${config.ResourceFile} not found, run 'npm run collect'`);
    }

    const graphFactory = new GraphFactory(this,'GraphFactory',resources, config);

    for (let widget of graphFactory.getWidgets()){
      dashboard.addWidgets(widget);
    }
  }
}
