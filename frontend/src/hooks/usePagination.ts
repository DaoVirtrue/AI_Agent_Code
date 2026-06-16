import { useState, useCallback, useEffect, useRef } from 'react';

interface PaginationResult<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
  onChange: (page: number, pageSize?: number) => void;
  refresh: () => void;
  setData: (data: T[]) => void;
}

interface UsePaginationOptions {
  defaultPage?: number;
  defaultPageSize?: number;
}

export function usePagination<T>(
  fetchFn: (params: { page: number; pageSize: number }) => Promise<{ items: T[]; total: number }>,
  options: UsePaginationOptions = {}
): PaginationResult<T> {
  const { defaultPage = 1, defaultPageSize = 10 } = options;
  const [data, setData] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(defaultPage);
  const [pageSize, setPageSize] = useState(defaultPageSize);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetchRef = useRef(fetchFn);

  fetchRef.current = fetchFn;

  const load = useCallback(async (p: number, ps: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchRef.current({ page: p, pageSize: ps });
      setData(result.items || []);
      setTotal(result.total || 0);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch data';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(page, pageSize);
  }, [load, page, pageSize]);

  const onChange = useCallback((newPage: number, newPageSize?: number) => {
    if (newPageSize && newPageSize !== pageSize) {
      setPageSize(newPageSize);
      setPage(1);
      return;
    }
    setPage(newPage);
  }, [pageSize]);

  const refresh = useCallback(() => {
    load(page, pageSize);
  }, [load, page, pageSize]);

  return {
    data,
    total,
    page,
    pageSize,
    loading,
    error,
    onChange,
    refresh,
    setData,
  };
}
