import Editor from "@monaco-editor/react";

type Props = {
  value: unknown;
};

export function Inspector({ value }: Props) {
  return (
    <div className="inspector">
      <Editor
        height="100%"
        defaultLanguage="json"
        value={JSON.stringify(value, null, 2)}
        theme="vs-dark"
        options={{
          readOnly: true,
          minimap: { enabled: false },
          fontSize: 12,
          scrollBeyondLastLine: false,
          wordWrap: "on",
          automaticLayout: true
        }}
      />
    </div>
  );
}
