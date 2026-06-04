type Props = {
  value: unknown;
};

export function Inspector({ value }: Props) {
  const serialized =
    value === undefined ? "No detail payload is available yet." : JSON.stringify(value, null, 2);

  return (
    <div className="inspector">
      <pre>{serialized}</pre>
    </div>
  );
}
