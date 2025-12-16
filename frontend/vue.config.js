module.exports = {
  publicPath: '/',
  runtimeCompiler: true,
  chainWebpack: config => {
    config
        .plugin('html')
        .tap(args => {
            args[0].title = "PathBlocker v0.2";
            return args;
        })
  },
  // devServer Options don't belong into `configureWebpack`
  devServer: {
    host: '0.0.0.0',
    port: 8080,
    hot: true,
    allowedHosts: 'all',
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        pathRewrite: { '^/api': '' }
      }
    }
  },
};
