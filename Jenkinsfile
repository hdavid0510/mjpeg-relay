pipeline{

	agent any

	environment {
		IMAGE_NAME="hdavid0510/mjpeg-relay"
		IMAGE_TAG="dev"
		REGISTRY_CREDENTIALS=credentials('dockerhub-credential')
	}

	stages {
		stage('Init') {
			steps {
				echo 'Initializing.'

				sh 'echo $REGISTRY_CREDENTIALS_PSW | docker login -u $REGISTRY_CREDENTIALS_USR --password-stdin'
				echo "Running ${env.BUILD_ID} on ${env.JENKINS_URL}"
				echo "Building ${IMAGE_NAME} on branch ${IMAGE_TAG}"
			}
		}
		stage('Build/Push') {
			parallel {
				stage('linux/386'){
					steps {
						echo 'Building linux/386 image and pushing to DockerHub.'
						sh 'docker buildx build --push --platform linux/386 -t $IMAGE_NAME:$IMAGE_TAG .'
					}
				}
				stage('linux/amd64'){
					steps {
						echo 'Building linux/amd64 image and pushing to DockerHub.'
						sh 'docker buildx build --push --platform linux/amd64 -t $IMAGE_NAME:$IMAGE_TAG .'
					}
				}
				stage('linux/arm/v5'){
					steps {
						echo 'Building linux/arm/v5 image and pushing to DockerHub.'
						sh 'docker buildx build --push --platform linux/arm/v5 -t $IMAGE_NAME:$IMAGE_TAG .'
					}
				}
				stage('linux/arm/v7'){
					steps {
						echo 'Building linux/arm/v7 image and pushing to DockerHub.'
						sh 'docker buildx build --push --platform linux/arm/v7 -t $IMAGE_NAME:$IMAGE_TAG .'
					}
				}
				stage('linux/arm64'){
					steps {
						echo 'Building linux/arm64 image and pushing to DockerHub.'
						sh 'docker buildx build --push --platform linux/arm64 -t $IMAGE_NAME:$IMAGE_TAG .'
					}
				}
				stage('linux/ppc64le'){
					steps {
						echo 'Building linux/ppc64le image and pushing to DockerHub.'
						sh 'docker buildx build --push --platform linux/ppc64le -t $IMAGE_NAME:$IMAGE_TAG .'
					}
				}
				stage('linux/s390x'){
					steps {
						echo 'Building linux/s390x image and pushing to DockerHub.'
						sh 'docker buildx build --push --platform linux/s390x -t $IMAGE_NAME:$IMAGE_TAG .'
					}
				}
			}
		}
	}

	post {
		always {
			sh 'docker logout'
		}
	}

}
