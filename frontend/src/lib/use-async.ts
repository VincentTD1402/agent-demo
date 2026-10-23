import { useEffect, useState } from "react";

type State<T> = { data?: T; error?: string; loading: boolean };

/** Gọi hàm bất đồng bộ mỗi khi `deps` đổi; bỏ qua kết quả của lần gọi đã cũ. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ loading: true });
  useEffect(() => {
    let stale = false;
    setState({ loading: true });
    fn()
      .then((data) => !stale && setState({ data, loading: false }))
      .catch((e) => !stale && setState({ error: e instanceof Error ? e.message : "Lỗi", loading: false }));
    return () => {
      stale = true;
    };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}
