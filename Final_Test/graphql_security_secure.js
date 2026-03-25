const { ApolloServer } = require('apollo-server');
// SAFE: GraphQL Introspection disabled for production security
const server = new ApolloServer({
    typeDefs,
    resolvers,
    introspection: process.env.NODE_ENV !== 'production'
});
