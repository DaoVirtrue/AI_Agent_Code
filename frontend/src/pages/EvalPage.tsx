import { useEffect, useState } from 'react';
import { Card, Input, Button, Typography, Space, Tag, Table, Empty, Collapse, Descriptions, Alert } from 'antd';
import { ExperimentOutlined, ThunderboltOutlined, EyeOutlined } from '@ant-design/icons';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';
import { useAppStore } from '@/store';
import { useEvalStore } from '@/store/evalStore';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const fmt = (v: number | null | undefined) => (v == null ? '-' : v.toFixed(4));

export function EvalPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const {
    queries, expectedAnswers, isRunning, result, runs, error,
    setQueries, setExpectedAnswers, runEval, fetchRuns,
  } = useEvalStore();

  const [activeRun, setActiveRun] = useState<any>(null);

  useEffect(() => {
    setBreadcrumbs([{ title: '质量评测' }]);
    fetchRuns();
  }, [setBreadcrumbs, fetchRuns]);

  const radarData = result ? [
    { metric: '忠实度', value: Math.round(result.faithfulness * 100) },
    { metric: '答案相关性', value: Math.round(result.answer_relevancy * 100) },
    { metric: '上下文精确率', value: Math.round(result.context_precision * 100) },
    { metric: '上下文召回率', value: Math.round(result.context_recall * 100) },
  ] : [];

  const runColumns = [
    { title: 'Run ID', dataIndex: 'run_id', key: 'run_id', ellipsis: true },
    { title: 'Overall', dataIndex: ['scores', 'overall_score'], key: 'overall', render: (v: number) => v?.toFixed(4) },
    { title: '忠实度', dataIndex: ['scores', 'faithfulness'], key: 'faithfulness', render: (v: number) => v?.toFixed(4) },
    { title: '相关性', dataIndex: ['scores', 'answer_relevancy'], key: 'relevancy', render: (v: number) => v?.toFixed(4) },
    { title: '查询数', dataIndex: ['scores', 'num_queries'], key: 'n' },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => setActiveRun(record)}>查看内容</Button>
      ),
    },
  ];

  // per_query comes from the current result, or from a selected historical run
  const perQuery = activeRun?.scores?.per_query || result?.per_query || [];

  const renderQuery = (p: any, idx: number) => (
    <div key={idx} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <Tag color="geekblue">#{idx + 1}</Tag>
        <Text strong>{p.query}</Text>
        <Tag color="purple">综合 {fmt(p.scores?.overall)}</Tag>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="bg-gray-50 dark:bg-gray-800 rounded p-3">
          <Text type="secondary" className="block mb-1 text-xs">AI 生成答案</Text>
          <Paragraph className="!mb-0 whitespace-pre-wrap text-sm">{p.generated_answer || '(空)'}</Paragraph>
        </div>
        <div className="bg-blue-50 dark:bg-blue-900/10 rounded p-3">
          <Text type="secondary" className="block mb-1 text-xs">参考答案（若有）</Text>
          <Paragraph className="!mb-0 whitespace-pre-wrap text-sm">{p.expected_answer || <Text type="secondary">未提供参考答案</Text>}</Paragraph>
        </div>
      </div>

      <div>
        <Text type="secondary" className="block mb-1 text-xs">检索到的上下文（{p.retrieved_contexts?.length || 0} 条）</Text>
        {p.retrieved_contexts?.length ? (
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {p.retrieved_contexts.map((c: string, ci: number) => (
              <div key={ci} className="text-xs text-gray-500 bg-gray-50 dark:bg-gray-800 rounded px-2 py-1 border border-gray-100 dark:border-gray-700">
                [{ci + 1}] {c.substring(0, 200)}{c.length > 200 ? '…' : ''}
              </div>
            ))}
          </div>
        ) : (
          <Text type="secondary" className="text-xs">无检索上下文（知识库为空，忠实度计为 0）</Text>
        )}
      </div>

      <div className="flex gap-2 flex-wrap">
        <Tag color="green">忠实度 {fmt(p.scores?.faithfulness)}</Tag>
        <Tag color="cyan">相关性 {fmt(p.scores?.answer_relevancy)}</Tag>
        <Tag color="orange">精确率 {fmt(p.scores?.context_precision)}</Tag>
        <Tag color="magenta">召回率 {fmt(p.scores?.context_recall)}</Tag>
        {p.scores?.answer_correctness != null && <Tag color="red">正确性 {fmt(p.scores?.answer_correctness)}</Tag>}
      </div>
    </div>
  );

  return (
    <div className="space-y-4 animate-fade-in">
      <Title level={4} className="!mb-0">RAGAS 质量评测</Title>

      <Card title={<span className="flex items-center gap-2"><ExperimentOutlined /> 发起评测</span>}>
        <Space direction="vertical" className="w-full" size="middle">
          <div>
            <Text strong className="block mb-2">测试查询（每行一条）</Text>
            <TextArea
              rows={4}
              value={queries}
              onChange={(e) => setQueries(e.target.value)}
              placeholder={'报销的交通费上限是多少？\n请假的审批流程是什么？'}
            />
          </div>
          <div>
            <Text strong className="block mb-2">参考答案（可选，每行一条，用于正确性评测）</Text>
            <TextArea
              rows={3}
              value={expectedAnswers}
              onChange={(e) => setExpectedAnswers(e.target.value)}
              placeholder="市内交通实报实销，上限 200 元/天..."
            />
          </div>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={runEval}
            loading={isRunning}
            disabled={!queries.trim()}
            style={{ background: 'linear-gradient(135deg, #1677ff, #722ed1)', border: 'none' }}
          >
            运行评测
          </Button>
          <Text type="secondary" className="text-xs">
            评测会对每条查询执行「检索 + 生成」，并在下方展示 AI 生成内容、参考答案与检索上下文，供人工比对打分。
          </Text>
        </Space>
      </Card>

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card title="RAGAS 指标雷达图">
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="80%">
                <PolarGrid />
                <PolarAngleAxis dataKey="metric" />
                <PolarRadiusAxis domain={[0, 100]} />
                <Radar dataKey="value" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </Card>
          <Card title="指标明细">
            <div className="space-y-3">
              <div>
                <Text strong>综合得分: </Text>
                <Text type="success">{result.overall_score.toFixed(4)}</Text>
              </div>
              <div>
                <Text strong>忠实度 (Faithfulness): </Text>
                <Text>{result.faithfulness.toFixed(4)}</Text>
              </div>
              <div>
                <Text strong>答案相关性 (Relevancy): </Text>
                <Text>{result.answer_relevancy.toFixed(4)}</Text>
              </div>
              <div>
                <Text strong>上下文精确率 (Precision): </Text>
                <Text>{result.context_precision.toFixed(4)}</Text>
              </div>
              <div>
                <Text strong>上下文召回率 (Recall): </Text>
                <Text>{result.context_recall.toFixed(4)}</Text>
              </div>
              {result.answer_correctness != null && (
                <div>
                  <Text strong>答案正确性 (Correctness): </Text>
                  <Text>{result.answer_correctness.toFixed(4)}</Text>
                </div>
              )}
              {result.run_id && <Tag color="blue">run_id: {result.run_id}</Tag>}
            </div>
          </Card>
        </div>
      )}

      {error && <Text type="danger">{error}</Text>}

      {(activeRun || result) && (
        <Card
          title={<span className="flex items-center gap-2"><EyeOutlined /> AI 生成内容与人工比对</span>}
          extra={activeRun ? <Button size="small" onClick={() => setActiveRun(null)}>返回当前评测</Button> : null}
        >
          {activeRun && (
            <Alert type="info" showIcon className="mb-3" message={`查看历史评测 run: ${activeRun.run_id}`} />
          )}
          {perQuery.length === 0 ? (
            <Empty description="该评测没有逐条内容（旧数据）" />
          ) : (
            <div className="space-y-3">{perQuery.map(renderQuery)}</div>
          )}
        </Card>
      )}

      <Card title="历史评测记录">
        {runs.length === 0 ? (
          <Empty description="暂无评测记录" />
        ) : (
          <Table
            columns={runColumns}
            dataSource={runs}
            rowKey="run_id"
            pagination={{ pageSize: 10 }}
            size="small"
          />
        )}
      </Card>
    </div>
  );
}
