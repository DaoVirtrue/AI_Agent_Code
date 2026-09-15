import { useEffect } from 'react';
import { Card, Input, Button, Typography, Space, Tag, Table, Empty } from 'antd';
import { ExperimentOutlined, ThunderboltOutlined } from '@ant-design/icons';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';
import { useAppStore } from '@/store';
import { useEvalStore } from '@/store/evalStore';

const { TextArea } = Input;
const { Title, Text } = Typography;

export function EvalPage() {
  const setBreadcrumbs = useAppStore((s) => s.setBreadcrumbs);
  const {
    queries, expectedAnswers, isRunning, result, runs, error,
    setQueries, setExpectedAnswers, runEval, fetchRuns,
  } = useEvalStore();

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
  ];

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
              placeholder={'什么是 RAG？\n向量检索和关键词检索的区别？'}
            />
          </div>
          <div>
            <Text strong className="block mb-2">参考答案（可选，每行一条，用于正确性评测）</Text>
            <TextArea
              rows={3}
              value={expectedAnswers}
              onChange={(e) => setExpectedAnswers(e.target.value)}
              placeholder="RAG 是检索增强生成..."
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
