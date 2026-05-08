import { WidgetSet } from '../types/widget-set';
import { GraphWidget, Metric, Row, Statistic, TextWidget } from 'aws-cdk-lib/aws-cloudwatch';
import { Duration } from 'aws-cdk-lib';
import { Construct } from 'constructs';

export class MediaLiveWidgetSet extends Construct implements WidgetSet {
  widgetSet: any = [];
  namespace: string = 'AWS/MediaLive';
  alarmSet: any = [];

  constructor(scope: Construct, id: string, resource: any, _config: any) {
    super(scope, id);
    const Pipeline = resource.Pipeline;
    const ChannelId = resource.id;
    const region = resource.ResourceARN.split(':')[3];
    const markDown =
      '**MediaLive Channel  [' +
      ChannelId +
      '](https://' +
      region +
      '.console.aws.amazon.com/medialive/home?region=' +
      region +
      '#/channels/' +
      ChannelId +
      ')**';
    this.widgetSet.push(
      new TextWidget({
        markdown: markDown,
        width: 24,
        height: 1,
      }),
    );

    const activeAlerts = [];
    const networkIn = [];
    const networkOut = [];
    const inputVideoFrameRate = [];
    const fillMill = [];
    const inputLossSeconds = [];
    const droppedFrames = [];
    const output4xxErros = [];
    const output5xxErros = [];

    if (Pipeline.length != 0) {
      for (const Pipelines of Pipeline) {
        const pipelineId = Pipelines.PipelineId;
        const metricActiveAlerts = new Metric({
          namespace: this.namespace,
          metricName: 'ActiveAlerts',
          dimensionsMap: {
            ChannelId: ChannelId,
            Pipeline: pipelineId,
          },
          statistic: Statistic.MAXIMUM,
          period: Duration.minutes(1),
        });
        activeAlerts.push(metricActiveAlerts);

        const metricNetworkIn = new Metric({
          namespace: this.namespace,
          metricName: 'NetworkIn',
          dimensionsMap: {
            ChannelId: ChannelId,
            Pipeline: pipelineId,
          },
          statistic: Statistic.AVERAGE,
          period: Duration.minutes(1),
        });
        networkIn.push(metricNetworkIn);

        const metricNetworkOut = new Metric({
          namespace: this.namespace,
          metricName: 'NetworkOut',
          dimensionsMap: {
            ChannelId: ChannelId,
            Pipeline: pipelineId,
          },
          statistic: Statistic.AVERAGE,
          period: Duration.minutes(1),
        });
        networkOut.push(metricNetworkOut);

        const metricInputVideoFrameRate = new Metric({
          namespace: this.namespace,
          metricName: 'InputVideoFrameRate',
          dimensionsMap: {
            ChannelId: ChannelId,
            Pipeline: pipelineId,
          },
          statistic: Statistic.AVERAGE,
          period: Duration.minutes(1),
        });
        inputVideoFrameRate.push(metricInputVideoFrameRate);

        const metricFillMsec = new Metric({
          namespace: this.namespace,
          metricName: 'FillMsec',
          dimensionsMap: {
            ChannelId: ChannelId,
            Pipeline: pipelineId,
          },
          statistic: Statistic.AVERAGE,
          period: Duration.minutes(1),
        });
        fillMill.push(metricFillMsec);

        const metricInputLossSec = new Metric({
          namespace: this.namespace,
          metricName: 'InputLossSeconds',
          dimensionsMap: {
            ChannelId: ChannelId,
            Pipeline: pipelineId,
          },
          statistic: Statistic.SUM,
          period: Duration.minutes(1),
        });
        inputLossSeconds.push(metricInputLossSec);

        const metricDroppedFrames = new Metric({
          namespace: this.namespace,
          metricName: 'DroppedFrames',
          dimensionsMap: {
            Pipeline: pipelineId,
          },
          statistic: Statistic.SUM,
          period: Duration.minutes(1),
        });
        droppedFrames.push(metricDroppedFrames);

        const metricOutput4xxErrors = new Metric({
          namespace: this.namespace,
          metricName: 'Output4xxErrors',
          dimensionsMap: {
            Pipeline: pipelineId,
          },
          statistic: Statistic.SUM,
          period: Duration.minutes(1),
        });
        output4xxErros.push(metricOutput4xxErrors);

        const metricOutput5xxErrors = new Metric({
          namespace: this.namespace,
          metricName: 'Output5xxErrors',
          dimensionsMap: {
            Pipeline: pipelineId,
          },
          statistic: Statistic.SUM,
          period: Duration.minutes(1),
        });
        output5xxErros.push(metricOutput5xxErrors);
      }
      const ActiveAlerts = new GraphWidget({
        title: 'Active alerts',
        region: region,
        left: activeAlerts,
        width: 8,
      });
      const NetworkIn = new GraphWidget({
        title: 'Network in (Mbps)',
        region: region,
        left: networkIn,
        width: 8,
      });
      const NetworkOut = new GraphWidget({
        title: 'Network out (Mbps)',
        region: region,
        right: networkOut,
        width: 8,
      });

      const InputVideoFrameRate = new GraphWidget({
        title: 'Input video frame rate ',
        region: region,
        left: inputVideoFrameRate,
        width: 12,
      });

      const FillMsec = new GraphWidget({
        title: 'Fill milliseconds',
        region: region,
        left: fillMill,
        width: 12,
      });

      const InputLossSeconds = new GraphWidget({
        title: 'Input Loss Seconds',
        region: region,
        left: inputLossSeconds,
        width: 6,
      });

      const DroppedFrames = new GraphWidget({
        title: 'Dropped Frames',
        region: region,
        left: droppedFrames,
        width: 6,
      });

      const Output4xxErros = new GraphWidget({
        title: 'Output 4xx Errors',
        region: region,
        left: output4xxErros,
        width: 6,
      });

      const Output5xxErros = new GraphWidget({
        title: 'Output 5xx Errors',
        region: region,
        left: output5xxErros,
        width: 6,
      });
      this.widgetSet.push(
        new Row(
          ActiveAlerts,
          NetworkIn,
          NetworkOut,
          InputVideoFrameRate,
          FillMsec,
          InputLossSeconds,
          DroppedFrames,
          Output4xxErros,
          Output5xxErros,
        ),
      );
    }
  }
  getWidgetSets(): [] {
    return this.widgetSet;
  }

  getAlarmSet(): [] {
    return this.alarmSet;
  }
}
