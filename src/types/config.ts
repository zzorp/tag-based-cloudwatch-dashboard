import { z } from 'zod';

export const AlarmDashboardSchema = z.object({
  enabled: z.boolean().default(false),
  organizationId: z.string().default(''),
  alarmViewListSize: z.number().default(100),
});

export const MetricDashboardsSchema = z.object({
  enabled: z.boolean().default(true),
});

export const ConfigSchema = z.object({
  BaseName: z.string(),
  ResourceFile: z.string(),
  TagKey: z.string(),
  TagValues: z.array(z.string()),
  Regions: z.array(z.string()),
  GroupingTagKey: z.string().optional().default(''),
  CustomEC2TagKeys: z.array(z.string()).optional().default([]),
  CustomNamespaceFile: z.string(),
  Compact: z.boolean(),
  CompactMaxResourcesPerWidget: z.number(),
  AlarmTopic: z.string().optional().default(''),
  AlarmDashboard: AlarmDashboardSchema.optional().default({ enabled: false, organizationId: '', alarmViewListSize: 100 }),
  MetricDashboards: MetricDashboardsSchema.optional().default({ enabled: true }),
});

export type AppConfig = z.infer<typeof ConfigSchema>;
export type AlarmDashboardConfig = z.infer<typeof AlarmDashboardSchema>;
export type MetricDashboardsConfig = z.infer<typeof MetricDashboardsSchema>;
