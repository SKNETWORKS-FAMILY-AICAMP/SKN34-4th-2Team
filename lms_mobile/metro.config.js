const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const projectRoot = __dirname;
const webSrc = path.resolve(projectRoot, '../lms_react/src');
const config = getDefaultConfig(projectRoot);

config.watchFolders = [webSrc];
config.resolver.nodeModulesPaths = [path.resolve(projectRoot, 'node_modules')];

const upstream = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName.startsWith('@web/')) {
    return context.resolveRequest(context, path.join(webSrc, moduleName.slice('@web/'.length)), platform);
  }
  if (upstream) return upstream(context, moduleName, platform);
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
