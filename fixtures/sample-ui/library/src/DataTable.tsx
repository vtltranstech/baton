export interface Column {
  key: string;
  header: string;
}

export interface DataTableProps<T> {
  rows: T[];
  columns: Column[];
  caption: string;
}

export const DataTable = <T,>(props: DataTableProps<T>) => {
  return <table aria-label={props.caption} />;
};
