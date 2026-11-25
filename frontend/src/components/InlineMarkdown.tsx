import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

/** Renders short text (quiz questions, options) with inline Markdown + LaTeX math, without block wrappers. */
export default function InlineMarkdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
      components={{ p: ({ children }) => <span>{children}</span> }}
    >
      {text}
    </ReactMarkdown>
  );
}
