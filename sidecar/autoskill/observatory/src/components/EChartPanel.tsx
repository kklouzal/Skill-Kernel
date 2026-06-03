import { useEffect, useRef } from "react";
import { BarChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent
} from "echarts/components";
import { init, use, type EChartsCoreOption } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use([
  BarChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer
]);

type Props = {
  title: string;
  option: EChartsCoreOption;
};

export function EChartPanel({ title, option }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = init(ref.current, "dark", { renderer: "canvas" });
    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [option]);

  return (
    <section className="chart-panel">
      <header>{title}</header>
      <div ref={ref} className="chart-surface" />
    </section>
  );
}
