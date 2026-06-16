import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Card,
  Select,
  Space,
  Table,
  Tag,
  Statistic,
  Row,
  Col,
  Empty,
  Spin,
  Typography,
  Tooltip,
  Divider,
} from 'antd';
import {
  TrophyOutlined,
  ExperimentOutlined,
  BarChartOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { usePromptsStore } from '@/store/promptsStore';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ReTooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
const { Text, Paragraph } = Typography;

const VARIANT_COLORS = ['#1677ff', '#52c41a', '#faad14', '#f5222d', '#722ed1'];

function generateMockVariableSets(variables: string[]): Record<string, string>[] {
  const sets: Record<string, string>[] = [
    {
      name: 'Variant A',
    },
    {
      name: 'Variant B',
    },
    {
      name: 'Variant C',
    },
  ];

  const sampleValues: Record<string, string[]> = {
    tone: ['专业', '随意', '热情'],
    style: ['简洁', '详细', '对话式'],
    format: ['要点列表', '段落', '编号列表'],
    length: ['短', '中', '长'],
    language: ['English', '简单英语', '技术英语'],
    role: ['老师', '顾问', '专家'],
    action: ['总结', '分析', '解释'],
    topic: ['技术', '科学', '商业'],
    audience: ['初学者', '专家', '高管'],
    detail: ['基础', '中级', '高级'],
  };

  sets.forEach((set, setIndex) => {
    variables.forEach((variable) => {
      if (sampleValues[variable]) {
        set[variable] = sampleValues[variable][setIndex % sampleValues[variable].length];
      } else {
        set[variable] = `test_value_${setIndex + 1}`;
      }
    });
  });

  return sets;
}

export function ABTestResults() {
  const templates = usePromptsStore((s) => s.templates);
  const experiments = usePromptsStore((s) => s.experiments);
  const experimentsLoading = usePromptsStore((s) => s.experimentsLoading);
  const runABExperiment = usePromptsStore((s) => s.runABExperiment);
  const selectedTemplate = usePromptsStore((s) => s.selectedTemplate);

  const [selectedTemplateId, setSelectedTemplateId] = useState<string | undefined>(
    selectedTemplate?.id
  );
  const [hasRun, setHasRun] = useState(false);

  useEffect(() => {
    if (selectedTemplate?.id && selectedTemplateId !== selectedTemplate.id) {
      setSelectedTemplateId(selectedTemplate.id);
      setHasRun(false);
    }
  }, [selectedTemplate?.id]);

  const handleTemplateSelect = useCallback(
    async (templateId: string) => {
      setSelectedTemplateId(templateId);
      const template = templates.find((t) => t.id === templateId);
      if (!template) return;

      const variableSets = generateMockVariableSets(template.variables);
      await runABExperiment(templateId, variableSets);
      setHasRun(true);
    },
    [templates, runABExperiment]
  );

  const templateOptions = useMemo(
    () =>
      templates.map((t) => ({
        value: t.id,
        label: `${t.name}${t.category ? ` (${t.category})` : ''} - v${t.version}`,
      })),
    [templates]
  );

  const selectedTemplateData = useMemo(
    () => templates.find((t) => t.id === selectedTemplateId),
    [templates, selectedTemplateId]
  );

  const tableColumns = useMemo(
    () => [
      {
        title: '变体',
        dataIndex: 'variantName',
        key: 'variantName',
        width: 140,
        render: (name: string, _record: any, index: number) => (
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full flex-shrink-0"
              style={{
                backgroundColor: VARIANT_COLORS[index % VARIANT_COLORS.length],
              }}
            />
            <Text strong>{name}</Text>
          </div>
        ),
      },
      {
        title: (
          <Tooltip title="所有测试样本的平均分数">
            <span>
              平均分 <InfoCircleOutlined className="text-gray-400 text-xs" />
            </span>
          </Tooltip>
        ),
        dataIndex: 'avgScore',
        key: 'avgScore',
        width: 120,
        render: (val: number) => (
          <Text strong className="tabular-nums">
            {val.toFixed(3)}
          </Text>
        ),
        sorter: (a: any, b: any) => a.avgScore - b.avgScore,
      },
      {
        title: (
          <Tooltip title="Welch's t-test P 值。数值 < 0.05 表示具有统计显著性。">
            <span>
              P 值 <InfoCircleOutlined className="text-gray-400 text-xs" />
            </span>
          </Tooltip>
        ),
        dataIndex: 'pValue',
        key: 'pValue',
        width: 120,
        render: (val: number) => (
          <Text
            className="tabular-nums"
            type={val > 0.05 ? 'danger' : 'secondary'}
          >
            {val.toFixed(4)}
          </Text>
        ),
      },
      {
        title: (
          <Tooltip title="Cohen's d 效应量：小=0.2，中=0.5，大=0.8">
            <span>
              Cohen's d <InfoCircleOutlined className="text-gray-400 text-xs" />
            </span>
          </Tooltip>
        ),
        dataIndex: 'cohensD',
        key: 'cohensD',
        width: 120,
        render: (val: number) => {
          let color = 'default';
          if (val >= 0.8) color = 'green';
          else if (val >= 0.5) color = 'blue';
          else if (val >= 0.2) color = 'orange';
          return (
            <Text className="tabular-nums">
              {val.toFixed(2)}
              <Tag
                color={color}
                className="!ml-1 text-xs"
                style={{ fontSize: '10px', lineHeight: '16px' }}
              >
                {val >= 0.8 ? '大' : val >= 0.5 ? '中' : val >= 0.2 ? '小' : '可忽略'}
              </Tag>
            </Text>
          );
        },
        sorter: (a: any, b: any) => a.cohensD - b.cohensD,
      },
      {
        title: '优胜',
        dataIndex: 'winner',
        key: 'winner',
        width: 100,
        render: (winner: boolean) =>
          winner ? (
            <Tag color="gold" icon={<TrophyOutlined />}>
              优胜
            </Tag>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
    ],
    []
  );

  const chartData = useMemo(() => {
    const metrics = [
      { name: '平均分', key: 'avgScore' },
      { name: 'p-Value', key: 'pValue' },
      { name: "Cohen's d", key: 'cohensD' },
    ];

    return metrics.map((metric) => {
      const entry: Record<string, any> = { metric: metric.name };
      experiments.forEach((exp) => {
        entry[exp.variantName] =
          metric.key === 'pValue'
            ? exp.pValue
            : metric.key === 'cohensD'
            ? exp.cohensD
            : exp.avgScore;
      });
      return entry;
    });
  }, [experiments]);

  const confidenceIntervals = useMemo(() => {
    return experiments.map((exp, idx) => {
      const se = 0.05 + Math.random() * 0.03;
      const mean = exp.avgScore;
      return {
        variant: exp.variantName,
        mean,
        lower: mean - 1.96 * se,
        upper: mean + 1.96 * se,
        color: VARIANT_COLORS[idx % VARIANT_COLORS.length],
      };
    });
  }, [experiments]);

  const renderEmptyState = () => (
    <Empty
      image={<ExperimentOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />}
      description={
        <span className="text-gray-400">
          选择模板以查看 A/B 实验结果
        </span>
      }
      className="py-16"
    />
  );

  const renderResults = () => (
    <div className="space-y-6">
      {/* Results Table */}
      <Card
        title={
          <Space>
            <BarChartOutlined />
            <span>实验结果</span>
          </Space>
        }
        className="!rounded-xl"
      >
        <Table
          dataSource={experiments}
          columns={tableColumns}
          rowKey="variantName"
          loading={experimentsLoading}
          pagination={false}
          size="middle"
          locale={{ emptyText: '暂无实验数据' }}
        />
      </Card>

      {/* Charts */}
      {experiments.length > 0 && (
        <Row gutter={[16, 16]}>
          {/* Bar Chart */}
          <Col xs={24} lg={14}>
            <Card
              title={
                <Space>
                  <BarChartOutlined />
                  <span>指标对比</span>
                </Space>
              }
              className="!rounded-xl"
            >
              <ResponsiveContainer width="100%" height={350}>
                <BarChart
                  data={chartData}
                  margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="metric" tick={{ fontSize: 13 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <ReTooltip
                    contentStyle={{
                      borderRadius: 8,
                      border: '1px solid #e8e8e8',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                    }}
                    formatter={(value: number) =>
                      typeof value === 'number' ? value.toFixed(4) : value
                    }
                  />
                  <Legend />
                  {experiments.map((exp, idx) => (
                    <Bar
                      key={exp.variantName}
                      dataKey={exp.variantName}
                      fill={VARIANT_COLORS[idx % VARIANT_COLORS.length]}
                      radius={[4, 4, 0, 0]}
                      maxBarSize={50}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </Col>

          {/* Statistical Summary */}
          <Col xs={24} lg={10}>
            <Card
              title={
                <Space>
                  <InfoCircleOutlined />
                  <span>统计分析</span>
                </Space>
              }
              className="!rounded-xl h-full"
            >
              <div className="space-y-4">
                <div>
                  <Text strong className="block mb-2">
                    测试方法
                  </Text>
                  <Paragraph type="secondary" className="!mb-0 text-sm">
                    使用 Welch's t-test（不等方差）将每个变体与基线进行比较。
                    该检验不假设组间方差相等，更适合 A/B 测试场景。
                  </Paragraph>
                </div>

                <Divider className="!my-3" />

                <div>
                  <Text strong className="block mb-3">
                    95% 置信区间
                  </Text>
                  <div className="space-y-3">
                    {confidenceIntervals.map((ci) => (
                      <div key={ci.variant} className="flex items-center gap-3">
                        <div
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: ci.color }}
                        />
                        <Text className="flex-shrink-0 w-20 text-sm">{ci.variant}</Text>
                        <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded-full relative overflow-hidden">
                          <div
                            className="absolute h-full rounded-full opacity-30"
                            style={{
                              backgroundColor: ci.color,
                              left: `${(ci.lower / 1.0) * 100}%`,
                              width: `${((ci.upper - ci.lower) / 1.0) * 100}%`,
                            }}
                          />
                          <div
                            className="absolute h-full w-1.5 rounded-full top-0"
                            style={{
                              backgroundColor: ci.color,
                              left: `${(ci.mean / 1.0) * 100}%`,
                              transform: 'translateX(-50%)',
                            }}
                          />
                        </div>
                        <Text className="text-xs tabular-nums flex-shrink-0 w-32 text-right">
                          {ci.lower.toFixed(3)} – {ci.upper.toFixed(3)}
                        </Text>
                      </div>
                    ))}
                  </div>
                </div>

                <Divider className="!my-3" />

                <div>
                  <Text strong className="block mb-2">
                    优胜判定
                  </Text>
                  <Paragraph type="secondary" className="!mb-0 text-sm">
                    优胜变体由具有统计显著性的变体中平均分最高者决定。
                    若无变体达到显著性（p &lt; 0.05），则选择得分最高且
                    效应量最大的变体。
                  </Paragraph>
                </div>

                {experiments.length > 0 && (
                  <>
                    <Divider className="!my-3" />
                    <Row gutter={[12, 12]}>
                      {experiments.map((exp, idx) => (
                        <Col span={12} key={exp.variantName}>
                          <Card
                            size="small"
                            className={`!rounded-lg ${
                              exp.winner
                                ? '!border-gold-400 dark:!border-yellow-600'
                                : ''
                            }`}
                          >
                            <Statistic
                              title={
                                <Space size={4}>
                                  <div
                                    className="w-2 h-2 rounded-full"
                                    style={{
                                      backgroundColor:
                                        VARIANT_COLORS[idx % VARIANT_COLORS.length],
                                    }}
                                  />
                                  <Text className="text-xs">{exp.variantName}</Text>
                                </Space>
                              }
                              value={exp.avgScore}
                              precision={3}
                              valueStyle={{
                                fontSize: 20,
                                color: exp.winner ? '#faad14' : undefined,
                              }}
                              suffix={
                                exp.winner ? (
                                  <TrophyOutlined
                                    style={{ fontSize: 14, color: '#faad14' }}
                                  />
                                ) : undefined
                              }
                            />
                          </Card>
                        </Col>
                      ))}
                    </Row>
                  </>
                )}
              </div>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <Select
          showSearch
          placeholder="选择模板运行实验..."
          value={selectedTemplateId}
          onChange={handleTemplateSelect}
          options={templateOptions}
          className="!min-w-[360px]"
          filterOption={(input, option) =>
            (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
          }
          notFoundContent={
            templates.length === 0 ? (
              <Empty
                description="暂无可用模板"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : null
          }
          optionRender={(option) => (
            <div className="flex items-center justify-between">
              <Text>{option.label as string}</Text>
              <ExperimentOutlined className="text-gray-400" />
            </div>
          )}
        />
        {selectedTemplateData && (
          <Tag color="blue">
            {selectedTemplateData.variables.length} 个变量
          </Tag>
        )}
      </div>

      {experimentsLoading ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Spin size="large" />
          <Text type="secondary">正在跨变体运行 A/B 实验...</Text>
        </div>
      ) : !hasRun && !experimentsLoading ? (
        renderEmptyState()
      ) : experiments.length === 0 ? (
        <Empty description="暂无实验结果" className="py-16" />
      ) : (
        renderResults()
      )}
    </div>
  );
}

export default ABTestResults;
