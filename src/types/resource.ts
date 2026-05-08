export interface ResourceTag {
  Key: string;
  Value: string;
}

export interface BaseResource {
  ResourceARN: string;
  Tags: ResourceTag[];
}

export interface Ec2Resource extends BaseResource {
  Volumes: any[];
  Instance: any;
  CPUCreditSpecs?: any;
  CWAgent?: string;
}

export interface LambdaResource extends BaseResource {
  Configuration: any;
}

export interface EcsResource extends BaseResource {
  cluster: any;
  services: any[];
}

export interface RdsResource extends BaseResource {
  MultiAZ?: boolean;
  Engine?: string;
  EngineMode?: string;
  DBClusterMembers?: any[];
  Endpoint?: string;
  ReaderEndpoint?: string;
  EngineVersion?: string;
  ReadReplicaIdentifiers?: string[];
  DBClusterInstanceClass?: string;
  StorageType?: string;
  Iops?: number;
  PerformanceInsightsEnabled?: boolean;
}

export interface DynamoDbResource extends BaseResource {
  type: string;
  wcu: number;
  rcu: number;
}

export interface ElbV2Resource extends BaseResource {
  Extras: any;
  TargetGroups: any[];
}

export interface ElbV1Resource extends BaseResource {
  Extras: any;
}

export interface ApiGatewayV1Resource extends BaseResource {
  name: string;
  endpointConfiguration: string;
  disableExecuteApiEndpoint: boolean;
  stages: any[];
}

export interface ApiGatewayV2Resource extends BaseResource {
  name: string;
  apiid: string;
  type: string;
  disableExecuteApiEndpoint: boolean;
  endpoint: string;
}

export interface AppSyncResource extends BaseResource {
  name: string;
  apiId: string;
  xrayEnabled: boolean;
  realtimeUri: string;
  graphqlUri: string;
}

export interface S3Resource extends BaseResource {
  BucketName: string;
  Encryption: any;
  Region: string;
}

export interface SqsResource extends BaseResource {
  Attributes: any;
}

export interface CloudFrontResource extends BaseResource {
  Id: string;
  ARN: string;
  DomainName: string;
  Aliases: any;
  Origins: any;
}

export interface EfsResource extends BaseResource {
  ThroughputMode: string;
}

export interface TgwResource extends BaseResource {
  attachments: any[];
}

export interface MediaPackageResource extends BaseResource {
  Id: string;
  ARN: string;
  IngestEndpoint: any[];
  OriginEndpoint: any[];
}

export interface MediaLiveResource extends BaseResource {
  ARN: string;
  id: string;
  Pipeline: any[];
}

export type DecoratedResource =
  | Ec2Resource
  | LambdaResource
  | EcsResource
  | RdsResource
  | DynamoDbResource
  | ElbV2Resource
  | ElbV1Resource
  | ApiGatewayV1Resource
  | ApiGatewayV2Resource
  | AppSyncResource
  | S3Resource
  | SqsResource
  | CloudFrontResource
  | EfsResource
  | TgwResource
  | MediaPackageResource
  | MediaLiveResource
  | BaseResource;
