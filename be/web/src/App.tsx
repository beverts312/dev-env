import { BrowserRouter, Route, Routes } from 'react-router'

import { Layout } from '@/components/Layout'
import { Config } from '@/pages/Config'
import { Mail } from '@/pages/Mail'
import { MyPrs } from '@/pages/MyPrs'
import { NotFound } from '@/pages/NotFound'
import { Reviews } from '@/pages/Reviews'
import { Usage } from '@/pages/Usage'
import { Home } from '@/pages/Home'
import { Workspaces } from '@/pages/Workspaces'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="prs" element={<MyPrs />} />
          <Route path="reviews" element={<Reviews />} />
          <Route path="workspaces" element={<Workspaces />} />
          <Route path="mail" element={<Mail />} />
          <Route path="usage" element={<Usage />} />
          <Route path="config" element={<Config />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
