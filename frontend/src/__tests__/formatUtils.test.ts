import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  formatNumber,
  formatCurrency,
  formatDate,
  formatDateRelative,
  formatDuration,
  formatBytes,
  truncateText,
} from '@/utils/format';

describe('formatUtils - 格式化工具函数', () => {
  describe('formatNumber', () => {
    it('formatNumber(1234) 使用 K 后缀格式化数字', () => {
      const result = formatNumber(1234);
      expect(result).toBe('1.23K');
    });

    it('formatNumber 正确处理百万级别的数字', () => {
      const result = formatNumber(5_200_000);
      expect(result).toBe('5.20M');
    });

    it('formatNumber 正确处理十亿级别的数字', () => {
      const result = formatNumber(3_500_000_000);
      expect(result).toBe('3.50B');
    });

    it('formatNumber 正确处理小于 1000 的数字', () => {
      const result = formatNumber(42);
      expect(result).toBe('42.00');
    });

    it('formatNumber 可指定小数位数', () => {
      const result = formatNumber(1234, 1);
      expect(result).toBe('1.2K');
    });

    it('formatNumber 对零值返回格式化结果', () => {
      const result = formatNumber(0);
      expect(result).toBe('0.00');
    });

    it('formatNumber 对 undefined 返回 "-"', () => {
      const result = formatNumber(undefined as unknown as number);
      expect(result).toBe('-');
    });

    it('formatNumber 对 null 返回 "-"', () => {
      const result = formatNumber(null as unknown as number);
      expect(result).toBe('-');
    });
  });

  describe('formatCurrency', () => {
    it('formatCurrency 格式化为美元货币格式（4位小数）', () => {
      const result = formatCurrency(0.0123);
      // The function uses 4 decimal places (minimumFractionDigits: 4)
      expect(result).toBe('$0.0123');
    });

    it('formatCurrency 格式化较大金额', () => {
      const result = formatCurrency(1500.5);
      expect(result).toBe('$1,500.5000');
    });

    it('formatCurrency 格式化零值', () => {
      const result = formatCurrency(0);
      expect(result).toBe('$0.0000');
    });

    it('formatCurrency 对 undefined 返回 "-"', () => {
      const result = formatCurrency(undefined as unknown as number);
      expect(result).toBe('-');
    });

    it('formatCurrency 对 null 返回 "-"', () => {
      const result = formatCurrency(null as unknown as number);
      expect(result).toBe('-');
    });

    it('formatCurrency 可指定货币类型', () => {
      const result = formatCurrency(99.99, 'EUR');
      // EUR format may have different symbol placement depending on platform
      expect(result).toContain('99.9900');
      expect(result).toMatch(/€|EUR/);
    });
  });

  describe('formatDate', () => {
    it('formatDate 使用默认格式格式化有效日期字符串', () => {
      const date = new Date(2025, 0, 15, 10, 30, 45); // Jan 15, 2025 10:30:45

      const result = formatDate(date);

      expect(result).toBe('2025-01-15 10:30:45');
    });

    it('formatDate 使用自定义格式', () => {
      const date = new Date(2025, 5, 1); // June 1, 2025

      const result = formatDate(date, 'YYYY/MM/DD');

      expect(result).toBe('2025/06/01');
    });

    it('formatDate 接受字符串日期', () => {
      const result = formatDate('2025-03-20');

      // dayjs will parse this and format with default format
      expect(result).toBe('2025-03-20 00:00:00');
    });

    it('formatDate 接受时间戳（毫秒）', () => {
      const timestamp = new Date(2025, 0, 1, 0, 0, 0).getTime();

      const result = formatDate(timestamp);

      expect(result).toBe('2025-01-01 00:00:00');
    });

    it('formatDate 对空字符串返回 "-"', () => {
      const result = formatDate('');

      expect(result).toBe('-');
    });

    it('formatDate 对 null 返回 "-"', () => {
      const result = formatDate(null as unknown as string);

      expect(result).toBe('-');
    });
  });

  describe('formatDateRelative', () => {
    it('formatDateRelative 返回相对时间字符串', () => {
      const now = new Date();
      const result = formatDateRelative(now);

      // "a few seconds ago" or similar
      expect(result).toBeTruthy();
      expect(typeof result).toBe('string');
      expect(result).not.toBe('-');
    });

    it('formatDateRelative 对空字符串返回 "-"', () => {
      const result = formatDateRelative('');

      expect(result).toBe('-');
    });
  });

  describe('formatDuration', () => {
    it('formatDuration(1500) 返回 "1.5s"（毫秒转为秒）', () => {
      const result = formatDuration(1500);

      expect(result).toBe('1.5s');
    });

    it('formatDuration 处理小于 1000 毫秒的时间', () => {
      const result = formatDuration(500);

      expect(result).toBe('500ms');
    });

    it('formatDuration 处理小于 60 秒的时间', () => {
      const result = formatDuration(30000);

      expect(result).toBe('30.0s');
    });

    it('formatDuration 处理分钟级别的时间', () => {
      const result = formatDuration(150000); // 2分30秒

      expect(result).toBe('2m 30s');
    });

    it('formatDuration 处理小时级别的时间', () => {
      const result = formatDuration(3_600_000 * 2 + 60_000 * 15); // 2h 15m

      expect(result).toBe('2h 15m');
    });

    it('formatDuration 处理零毫秒', () => {
      const result = formatDuration(0);

      expect(result).toBe('0ms');
    });

    it('formatDuration 对 undefined 返回 "-"', () => {
      const result = formatDuration(undefined as unknown as number);

      expect(result).toBe('-');
    });
  });

  describe('formatBytes', () => {
    it('formatBytes 格式化字节数', () => {
      expect(formatBytes(500)).toBe('500 B');
    });

    it('formatBytes 格式化千字节', () => {
      expect(formatBytes(2048)).toBe('2 KB');
    });

    it('formatBytes 格式化兆字节', () => {
      expect(formatBytes(5 * 1024 * 1024)).toBe('5 MB');
    });

    it('formatBytes 对零返回 "0 B"', () => {
      expect(formatBytes(0)).toBe('0 B');
    });

    it('formatBytes 对 null 返回 "-"', () => {
      expect(formatBytes(null as unknown as number)).toBe('-');
    });
  });

  describe('truncateText', () => {
    it('truncateText 截断超过最大长度的文本', () => {
      expect(truncateText('Hello World', 5)).toBe('Hello...');
    });

    it('truncateText 不截断短于最大长度的文本', () => {
      expect(truncateText('Hi', 10)).toBe('Hi');
    });

    it('truncateText 处理空字符串', () => {
      expect(truncateText('', 5)).toBe('');
    });

    it('truncateText 恰好等于最大长度时不截断', () => {
      expect(truncateText('Hello', 5)).toBe('Hello');
    });
  });
});
