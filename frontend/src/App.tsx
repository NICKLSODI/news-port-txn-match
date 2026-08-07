import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Today from './pages/Today'
import News from './pages/News'
import ArticlePage from './pages/Article'
import RmQueue from './pages/RmQueue'
import Customers from './pages/Customers'
import CustomerPage from './pages/Customer'
import Reports from './pages/Reports'
import Spec from './pages/Spec'
import Settings from './pages/Settings'
import Upload from './pages/Upload'
import Stock from './pages/Stock'
import Dividends from './pages/Dividends'
import Mail from './pages/Mail'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* หน้าแรกคือ "งานวันนี้ของ RM" — เปิดโปรแกรมมาต้องเห็นเลยว่าวันนี้ต้องทำอะไร
            ไม่ใช่ต้องเลือกหุ้นก่อนถึงจะรู้ ส่วน "หาจากหุ้น" ย้ายไป /stock */}
        <Route index element={<RmQueue />} />
        <Route path="today" element={<Today />} />
        <Route path="news" element={<News />} />
        <Route path="news/:id" element={<ArticlePage />} />
        {/* ลิงก์เก่าที่ชี้ /rm ยังต้องเข้าได้ — มีทั้งใน state ของหน้าอื่นและที่คนบุ๊กมาร์กไว้ */}
        <Route path="rm" element={<Navigate to="/" replace />} />
        <Route path="dividends" element={<Dividends />} />
        <Route path="stock" element={<Stock />} />
        <Route path="stock/:entity" element={<Stock />} />
        <Route path="customers" element={<Customers />} />
        <Route path="customers/:key" element={<CustomerPage />} />
        <Route path="reports" element={<Reports />} />
        <Route path="spec" element={<Spec />} />
        <Route path="upload" element={<Upload />} />
        <Route path="mail" element={<Mail />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
