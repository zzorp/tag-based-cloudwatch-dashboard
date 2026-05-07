import { ConfigSchema } from '../../src/types/config';

describe('Config Schema Validation', () => {
  const validConfig = {
    BaseName: 'TestApp',
    ResourceFile: './resources.json',
    TagKey: 'environment',
    TagValues: ['production'],
    Regions: ['us-east-1'],
    CustomNamespaceFile: './custom_namespaces.json',
    Compact: false,
    CompactMaxResourcesPerWidget: 10,
  };

  it('should parse a valid config successfully', () => {
    const result = ConfigSchema.parse(validConfig);
    expect(result.BaseName).toBe('TestApp');
    expect(result.ResourceFile).toBe('./resources.json');
    expect(result.TagKey).toBe('environment');
    expect(result.TagValues).toEqual(['production']);
    expect(result.Regions).toEqual(['us-east-1']);
    expect(result.Compact).toBe(false);
    expect(result.CompactMaxResourcesPerWidget).toBe(10);
  });

  it('should apply defaults for optional fields', () => {
    const result = ConfigSchema.parse(validConfig);
    expect(result.GroupingTagKey).toBe('');
    expect(result.CustomEC2TagKeys).toEqual([]);
    expect(result.AlarmTopic).toBe('');
    expect(result.AlarmDashboard).toEqual({
      enabled: false,
      organizationId: '',
      alarmViewListSize: 100,
    });
    expect(result.MetricDashboards).toEqual({
      enabled: true,
    });
  });

  it('should throw when BaseName is missing', () => {
    const { BaseName: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should throw when TagKey is missing', () => {
    const { TagKey: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should throw when ResourceFile is missing', () => {
    const { ResourceFile: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should throw when TagValues is missing', () => {
    const { TagValues: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should throw when Regions is missing', () => {
    const { Regions: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should throw when CustomNamespaceFile is missing', () => {
    const { CustomNamespaceFile: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should throw when Compact is missing', () => {
    const { Compact: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should throw when CompactMaxResourcesPerWidget is missing', () => {
    const { CompactMaxResourcesPerWidget: _, ...config } = validConfig;
    expect(() => ConfigSchema.parse(config)).toThrow();
  });

  it('should reject invalid types for BaseName', () => {
    expect(() => ConfigSchema.parse({ ...validConfig, BaseName: 123 })).toThrow();
  });

  it('should reject invalid types for TagValues', () => {
    expect(() => ConfigSchema.parse({ ...validConfig, TagValues: 'production' })).toThrow();
  });

  it('should reject invalid types for Compact', () => {
    expect(() => ConfigSchema.parse({ ...validConfig, Compact: 'true' })).toThrow();
  });

  it('should reject invalid types for CompactMaxResourcesPerWidget', () => {
    expect(() => ConfigSchema.parse({ ...validConfig, CompactMaxResourcesPerWidget: 'ten' })).toThrow();
  });

  it('should parse full config with all optional fields', () => {
    const fullConfig = {
      ...validConfig,
      GroupingTagKey: 'team',
      CustomEC2TagKeys: ['Project', 'Owner'],
      AlarmTopic: 'arn:aws:sns:us-east-1:123456789012:MyTopic',
      AlarmDashboard: {
        enabled: true,
        organizationId: 'o-1234567890',
        alarmViewListSize: 50,
      },
      MetricDashboards: {
        enabled: false,
      },
    };
    const result = ConfigSchema.parse(fullConfig);
    expect(result.GroupingTagKey).toBe('team');
    expect(result.CustomEC2TagKeys).toEqual(['Project', 'Owner']);
    expect(result.AlarmTopic).toBe('arn:aws:sns:us-east-1:123456789012:MyTopic');
    expect(result.AlarmDashboard.enabled).toBe(true);
    expect(result.AlarmDashboard.organizationId).toBe('o-1234567890');
    expect(result.AlarmDashboard.alarmViewListSize).toBe(50);
    expect(result.MetricDashboards.enabled).toBe(false);
  });
});
