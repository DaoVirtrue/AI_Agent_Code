/**
 * RAG 检索引擎 —— BM25 + 多策略增强
 *
 * ============================================================
 *  算法演进（面试可讲）：
 *  1. 朴素关键词匹配 → 停用词过滤 → TF-IDF → BM25 → 多策略融合
 * ============================================================
 *
 * BM25 公式:
 *   score(D,Q) = Σ IDF(qi) × f(qi,D) × (k1+1) / (f(qi,D) + k1×(1-b+b×|D|/avgDL))
 *
 *   其中: f(qi,D) = 词qi在文档D中的词频
 *         |D| = 文档长度, avgDL = 平均文档长度
 *         k1 = 1.5（词频饱和参数）, b = 0.75（长度归一化参数）
 *         IDF(qi) = log((N - df + 0.5) / (df + 0.5) + 1)
 *
 * 增强策略:
 *  2. 精确短语匹配加成 (+30%)
 *  3. 文档名匹配加成 (+25%)
 *  4. 关键词密度归一化
 *  5. 至少匹配 40% 非停用词查询词
 *  6. 多关键词时 MM 策略（most matching）
 */

const STOP_WORDS = new Set([
  '的','了','在','是','我','有','和','就','不','人','都','一','一个',
  '上','也','很','到','说','要','去','你','会','着','没有','看','好',
  '自己','这','他','她','它','们','那','什么','怎么','如何','为什么',
  '吗','呢','啊','吧','呀','哦','嗯','哈','哇','啦',
  '可以','觉得','知道','应该','可能','需要','已经','因为','所以',
  '但是','虽然','如果','还是','或者','不过','然后','之后','之前',
  '这个','那个','这些','那些','这里','那里','这样','那样',
  '用','做','让','给','把','被','从','对','与','以','及','或',
  '等','其','所','之','者','而','于','则','且','但','还','又','再',
  'a','an','the','is','are','was','were','be','been','being',
  'have','has','had','do','does','did','will','would','could',
  'should','may','might','can','shall','to','of','in','for',
  'on','with','at','by','from','as','into','through','during',
  'before','after','above','below','between','under',
  'no','nor','not','only','own','same','so','than','too',
  'very','just','about','now','also','up','out','off','over',
]);

export interface SearchResult {
  chunk_id: string;
  document_name: string;
  content: string;
  score: number;
  fullChunk?: string;
  matchDetails?: string;
}

// ── BM25 Implementation ────────────────────────────────────
const K1 = 1.5;  // term frequency saturation
const B = 0.75;  // length normalization

function computeIDF(N: number, df: number): number {
  return Math.log((N - df + 0.5) / (df + 0.5) + 1);
}

export function searchDocuments(query: string, docs: any[]): SearchResult[] {
  if (!query.trim() || docs.length === 0) return [];

  // 1. Extract and filter keywords (remove stop words)
  const rawKw = query.split(/[\s,，。！？、；：""''【】《》（）\(\)\[\]\{\}.]+/)
    .flatMap((k: string) => {
      if (k.length <= 3) return [k];
      return (k.match(/[a-zA-Z]+|[一-龥]{1,6}/g) || [k]).filter((p: string) => p.length > 1);
    })
    .map((k: string) => k.toLowerCase())
    .filter((k: string) => k.length > 1 && !STOP_WORDS.has(k));

  if (rawKw.length === 0) return [];

  // Deduplicate keywords
  const uniqueKw = [...new Set(rawKw)];
  const queryLower = query.toLowerCase();

  // 2. Collect all chunks for BM25 computation
  const allChunks: { doc: any; idx: number; text: string }[] = [];
  docs.forEach((doc: any) => {
    (doc.chunks || []).forEach((chunk: string, idx: number) => {
      allChunks.push({ doc, idx, text: chunk });
    });
  });

  const N = allChunks.length;
  if (N === 0) return [];

  // Average chunk length
  const avgDL = allChunks.reduce((s, c) => s + c.text.length, 0) / N;

  // 3. Compute document frequency for each keyword (for IDF)
  const df: Record<string, number> = {};
  uniqueKw.forEach(kw => { df[kw] = 0; });
  allChunks.forEach(ch => {
    const lower = ch.text.toLowerCase();
    uniqueKw.forEach(kw => {
      if (lower.includes(kw)) df[kw] = (df[kw] || 0) + 1;
    });
  });

  // 4. BM25 score each chunk + enhancements
  const scored: SearchResult[] = [];

  allChunks.forEach(ch => {
    const lower = ch.text.toLowerCase();
    const docName = (ch.doc.filename || '').toLowerCase();
    let bm25 = 0;
    let matchedKw = 0;
    const details: string[] = [];

    uniqueKw.forEach(kw => {
      if (!lower.includes(kw)) return;
      matchedKw++;
      // Term frequency
      const regex = new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const tf = (lower.match(regex) || []).length;
      // IDF
      const idf = computeIDF(N, df[kw] || 0);
      // BM25 score for this term
      const numerator = tf * (K1 + 1);
      const denominator = tf + K1 * (1 - B + B * ch.text.length / avgDL);
      bm25 += idf * numerator / denominator;
      details.push(`${kw}(tf=${tf},idf=${idf.toFixed(2)})`);
    });

    // Minimum match requirement: must match at least 40% of keywords (or at least 1 if only 1-2 keywords)
    const minMatch = uniqueKw.length <= 2 ? 1 : Math.ceil(uniqueKw.length * 0.4);
    if (matchedKw < minMatch) return;

    // ── Enhancements ──
    let boost = 0;

    // Exact phrase match: if the full query appears as a phrase
    if (lower.includes(queryLower) && queryLower.length > 2) {
      boost += 0.30;
      details.push('exact_phrase_match');
    }

    // Document name match: keyword appears in filename
    if (uniqueKw.some(kw => docName.includes(kw))) {
      boost += 0.25;
      details.push('name_match');
    }

    // Keyword density (occurrences per 1000 chars)
    const totalOcc = uniqueKw.reduce((s, kw) => {
      const r = new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      return s + (lower.match(r) || []).length;
    }, 0);
    const density = ch.text.length > 0 ? totalOcc * 1000 / ch.text.length : 0;
    if (density > 10) { boost += 0.10; details.push('high_density'); }

    const finalScore = Math.min(1, bm25 + boost);

    if (finalScore >= 0.10) {
      scored.push({
        chunk_id: `${ch.doc.document_id}_${ch.idx}`,
        document_name: ch.doc.filename,
        content: ch.text.substring(0, 300),
        score: finalScore,
        fullChunk: ch.text,
        matchDetails: details.join('|'),
      });
    }
  });

  return scored.sort((a, b) => b.score - a.score);
}

// ── Convenience: get top N full chunks ──────────────────────
export function getBestChunks(query: string, docs: any[], maxChunks: number = 3): string[] {
  return searchDocuments(query, docs).slice(0, maxChunks).map(r => r.fullChunk || r.content);
}
