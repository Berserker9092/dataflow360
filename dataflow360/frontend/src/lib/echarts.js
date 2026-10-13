// Enregistrement minimal d'ECharts (le bundle reste léger).
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart, FunnelChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
use([CanvasRenderer, LineChart, BarChart, PieChart, FunnelChart, GridComponent, TooltipComponent, LegendComponent])
