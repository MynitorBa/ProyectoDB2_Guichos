import api from './client'

export const getMyStoreConfig  = ()       => api.get('/vendor/store/config')
export const saveMyStoreConfig  = (data)   => api.put('/vendor/store/config', data)
export const getPublicStoreConfig = (vid)  => api.get(`/stores/${vid}/config`)
