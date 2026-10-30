export function ComingSoon({ title, children }: { title: string; children: string }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {children}
    </div>
  );
}
