type RunCardProps = {
  title?: string;
  status?: string;
};

export function RunCard({ title = "Run", status = "pending" }: RunCardProps) {
  return (
    <article className="panel">
      <h3>{title}</h3>
      <p>{status}</p>
    </article>
  );
}
